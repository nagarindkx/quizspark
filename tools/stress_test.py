#!/usr/bin/env python3
"""Black-box WebSocket load test for QuizSpark Docker v3.0/v3.1. Python 3.10+."""
import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
import json
import math
import os
from pathlib import Path
import random
import re
import ssl
import sys
import time
from urllib.parse import urlsplit
import uuid

import aiohttp


def distribution(values):
    values = sorted(v for v in values if v is not None)
    def pct(p):
        return round(values[min(len(values) - 1, math.ceil(p * len(values)) - 1)], 2) if values else None
    return {"samples": len(values), "p50": pct(.5), "p95": pct(.95), "p99": pct(.99),
            "max": round(values[-1], 2) if values else None}


def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


class TestFailure(Exception):
    pass


@dataclass
class Observation:
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    ready_at: float | None = None
    sent_at: float | None = None
    ack_at: float | None = None
    final_at: float | None = None
    final: dict | None = None
    schedule_lag_ms: float | None = None
    errors: list = field(default_factory=list)


STAGE = re.compile(r'"stage"\s*:\s*"([a-z]+)"')
INDEX = re.compile(r'"index"\s*:\s*(-?\d+)')
TYPE_STATE = re.compile(r'^\s*\{\s*"type"\s*:\s*"state"')
ME = re.compile(r'"me"\s*:\s*')
DECODER = json.JSONDecoder()


class Peer:
    def __init__(self, ws, role, label):
        self.ws, self.role, self.label = ws, role, label
        self.connected = asyncio.Event()
        self.changed = asyncio.Event()
        self.credentials = None
        self.state = None
        self.stages = {}
        self.observations = {}
        self.errors = []
        self.active_round = None
        self.expected_close = False
        self.disconnected = False
        self.messages = self.json_bytes = 0
        self.task = asyncio.create_task(self.read())

    def observation(self, index):
        if index not in self.observations:
            self.observations[index] = Observation()
        return self.observations[index]

    def question(self, index, me):
        now = time.perf_counter()
        obs = self.observation(index)
        if obs.ready_at is None:
            obs.ready_at = now
            obs.ready.set()
        if me.get("answered") and obs.sent_at is not None and obs.ack_at is None:
            obs.ack_at = now

    def fast_question(self, raw):
        """Skip decoding the repeated full roster; parse only this player's data.

        Optimized for v3.0's state envelope. Unrecognized layouts fall back to full JSON.
        """
        if self.role != "player" or not TYPE_STATE.search(raw[:80]):
            return False
        stage, index = STAGE.search(raw[:1024]), INDEX.search(raw[:1024])
        if not stage or stage.group(1) != "question" or not index:
            return False
        position = raw.rfind('"me"')
        match = ME.match(raw, position) if position >= 0 else None
        if not match:
            return False
        try:
            me, end = DECODER.raw_decode(raw, match.end())
            if not isinstance(me, dict) or "answered" not in me or raw[end:].strip() != "}}":
                return False
        except ValueError:
            return False
        self.question(int(index.group(1)), me)
        return True

    async def read(self):
        try:
            async for message in self.ws:
                if message.type == aiohttp.WSMsgType.ERROR:
                    raise TestFailure("websocket_receive_error")
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                raw = message.data
                self.messages += 1
                self.json_bytes += len(raw.encode("utf-8"))
                if self.fast_question(raw):
                    continue
                data = json.loads(raw)
                kind = data.get("type")
                if kind == "connected":
                    self.credentials = data
                    self.connected.set()
                elif kind == "error":
                    code = str(data.get("code", "unknown_error"))
                    self.errors.append(code)
                    if self.active_round is not None:
                        self.observation(self.active_round).errors.append(code)
                    self.changed.set()
                elif kind == "state":
                    self.state = state = data["state"]
                    index, stage = state["index"], state["stage"]
                    # Only the host waits for stage history. Keeping full rosters
                    # for every player/round would inflate long-test memory use.
                    if self.role == "host":
                        self.stages[(index, stage)] = state
                    if stage == "question":
                        self.question(index, state.get("me", {}))
                    elif stage == "results" and self.role == "player":
                        obs = self.observation(index)
                        obs.final = state.get("me", {})
                        obs.final_at = time.perf_counter()
                        if obs.final.get("answered") and obs.sent_at is not None and obs.ack_at is None:
                            obs.ack_at = obs.final_at
                    self.changed.set()
                elif kind == "kicked":
                    raise TestFailure("test_player_kicked")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.errors.append(type(error).__name__ + ":" + str(error)[:120])
        finally:
            if not self.expected_close:
                self.disconnected = True
            self.changed.set()

    async def wait_connected(self, timeout):
        async def wait():
            while not self.connected.is_set():
                if self.errors or self.disconnected:
                    raise TestFailure(self.errors[-1] if self.errors else "connection_closed")
                self.changed.clear()
                # The connected event is set by the receiver, independently of state delivery.
                connected = asyncio.create_task(self.connected.wait())
                changed = asyncio.create_task(self.changed.wait())
                try:
                    await asyncio.wait((connected, changed), return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in (connected, changed):
                        task.cancel()
                    await asyncio.gather(connected, changed, return_exceptions=True)
        await asyncio.wait_for(wait(), timeout)

    async def wait_stage(self, index, stage, timeout):
        async def wait():
            while (index, stage) not in self.stages:
                if self.disconnected:
                    raise TestFailure("host_disconnected")
                self.changed.clear()
                await self.changed.wait()
            return self.stages[(index, stage)]
        return await asyncio.wait_for(wait(), timeout)


class Runner:
    def __init__(self, args, password):
        self.args, self.password = args, password
        self.token = None
        self.http = None
        self.run_id = uuid.uuid4().hex[:8]
        self.report = {"created_utc": datetime.now(timezone.utc).isoformat(), "run_id": self.run_id,
                       "target": args.url, "settings": vars(args).copy(), "python": sys.version.split()[0],
                       "aiohttp": aiohttp.__version__, "cases": [], "notes": [
                           "Acknowledgement latency is send-to-first-state-confirmation, not network RTT.",
                           "Latency quantiles exclude answers with no acknowledgement; inspect lost answers too.",
                           "JSON bytes are uncompressed application payload, not wire bandwidth.",
                           "This is an HTTP/WebSocket protocol test, not a browser, image or Wi-Fi test."]}

    def save(self):
        path = Path(self.args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    async def api(self, method, path, body=None, authenticated=False):
        headers = {"Authorization": "Bearer " + self.token} if authenticated else {}
        async with self.http.request(method, self.args.url + path, json=body, headers=headers,
                                     allow_redirects=False) as response:
            if 300 <= response.status < 400:
                raise TestFailure(f"HTTP {response.status} redirect at {path}; use the final app URL")
            try:
                data = await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                raise TestFailure(f"HTTP {response.status} non-JSON response at {path}; check app URL/proxy") from None
            if response.status >= 400:
                code = data.get("error", "http_error") if isinstance(data, dict) else "http_error"
                raise TestFailure(f"HTTP {response.status}: {code} at {path}")
            return data

    async def peer(self, role, label):
        parts = urlsplit(self.args.url)
        origin = parts.scheme + "://" + parts.netloc
        ws = await self.http.ws_connect(self.args.url + "/ws", origin=origin,
                                       compress=15 if self.args.compression == "on" else 0,
                                       max_msg_size=8 * 1024 * 1024,
                                       timeout=aiohttp.ClientWSTimeout(ws_close=3))
        return Peer(ws, role, label)

    async def monitor(self, case, stop):
        """Measure generator lag independently of the HTTP health probe."""
        async def lag():
            while not stop.is_set():
                start = time.perf_counter()
                await asyncio.sleep(.2)
                case["_lag"].append(max(0, (time.perf_counter() - start - .2) * 1000))
        async def health():
            while not stop.is_set():
                started = time.perf_counter()
                try:
                    async with self.http.get(self.args.url + "/health", timeout=aiohttp.ClientTimeout(total=5),
                                             allow_redirects=False) as response:
                        await response.read()
                        if response.status != 200:
                            raise TestFailure("HTTP " + str(response.status))
                    case["_health"].append((time.perf_counter() - started) * 1000)
                except Exception as error:
                    case["health_errors"].append(type(error).__name__)
                await asyncio.sleep(1)
        jobs = [asyncio.create_task(lag()), asyncio.create_task(health())]
        try:
            await stop.wait()
        finally:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)

    async def case(self, count):
        args = self.args
        case = {"players_requested": count, "status": "running", "rounds": [], "join_errors": [],
                "cleanup_errors": [], "health_errors": [], "_health": [], "_lag": []}
        self.report["cases"].append(case)
        peers, host, quiz_id = [], None, None
        stop = asyncio.Event()
        monitor = asyncio.create_task(self.monitor(case, stop))
        cpu_started, wall_started = time.process_time(), time.perf_counter()
        try:
            quiz = {"title": f"[STRESS {self.run_id}] {count} players", "category": "Temporary load test",
                    "questions": [
                        {"type": "mcq", "text": f"Stress test {i + 1}: choose 4", "options": ["1", "2", "3", "4"],
                         "correct": 3, "time": args.question_seconds, "emoji": "🧪"}
                        if i % 2 == 0 else
                        {"type": "open", "text": f"Stress test {i + 1}: enter Au", "openAnswers": ["Au"],
                         "time": args.question_seconds, "emoji": "🧪"}
                        for i in range(args.rounds)]}
            quiz = await self.api("POST", "/api/quizzes", quiz, True)
            quiz_id = quiz["id"]
            case["temporary_quiz_id"] = quiz_id
            host = await self.peer("host", "host")
            await host.ws.send_json({"type": "create", "adminToken": self.token, "quizId": quiz_id})
            await host.wait_connected(args.timeout)
            pin = host.credentials["pin"]
            case["pin"] = pin
            log(f"{count} players: room {pin}; joining over {args.ramp_seconds:g}s")
            join_ms = []
            semaphore = asyncio.Semaphore(args.join_concurrency)
            join_start = time.perf_counter()
            async def join(i):
                scheduled = join_start + (args.ramp_seconds * i / max(count - 1, 1))
                await asyncio.sleep(max(0, scheduled - time.perf_counter()))
                async with semaphore:
                    started = time.perf_counter()
                    try:
                        peer = await self.peer("player", f"load-{i:04}")
                        peers.append(peer)
                        await peer.ws.send_json({"type": "join", "pin": pin,
                                                 "name": f"T{self.run_id}-{i:04}", "avatar": "🦊"})
                        await peer.wait_connected(args.timeout)
                        join_ms.append((time.perf_counter() - started) * 1000)
                    except Exception as error:
                        if isinstance(error, aiohttp.WSServerHandshakeError):
                            message = "websocket_handshake_HTTP_" + str(error.status)
                        else:
                            message = type(error).__name__ + ":" + str(error)[:150]
                        case["join_errors"].append({"player": i, "error": message})
            await asyncio.gather(*(join(i) for i in range(count)))
            case["players_joined"] = len(join_ms)
            case["join_ms"] = distribution(join_ms)
            case["join_elapsed_s"] = round(time.perf_counter() - join_start, 3)
            if len(join_ms) != count:
                raise TestFailure(f"Only {len(join_ms)}/{count} joined; inspect join_errors (including HTTP 429/rate_limit)")
            # All receivers must consume the final lobby before the measured question.
            async def settled():
                while not all(p.state and len(p.state.get("players", [])) == count for p in peers):
                    if any(p.disconnected for p in peers):
                        raise TestFailure("player_disconnected_in_lobby")
                    await asyncio.sleep(.05)
            await asyncio.wait_for(settled(), args.timeout)
            log(f"Joined {count}/{count}; join p95={case['join_ms']['p95']} ms")
            rng = random.Random(args.seed)
            for index in range(args.rounds):
                round_result = {"question": index + 1, "type": "mcq" if index % 2 == 0 else "open", "status": "running"}
                case["rounds"].append(round_result)
                if index:
                    await host.ws.send_json({"action": "leaderboard"})
                    await host.wait_stage(index - 1, "leaderboard", args.timeout)
                await host.ws.send_json({"action": "start" if index == 0 else "next"})
                await asyncio.wait_for(asyncio.gather(*(p.observation(index).ready.wait() for p in peers)), args.timeout)
                before_messages = sum(p.messages for p in peers + [host])
                before_bytes = sum(p.json_bytes for p in peers + [host])
                barrier = time.perf_counter() + args.think_seconds
                delays = [rng.uniform(0, args.answer_spread) if args.answer_spread else 0 for _ in peers]
                async def answer(peer, delay):
                    obs = peer.observation(index)
                    scheduled = barrier + delay
                    await asyncio.sleep(max(0, scheduled - time.perf_counter()))
                    peer.active_round = index
                    obs.sent_at = time.perf_counter()
                    obs.schedule_lag_ms = max(0, (obs.sent_at - scheduled) * 1000)
                    try:
                        await peer.ws.send_json({"type": "answer", "index": index, "value": 3 if index % 2 == 0 else "Au"})
                    except Exception as error:
                        obs.errors.append("send_" + type(error).__name__)
                await asyncio.gather(*(answer(p, delay) for p, delay in zip(peers, delays)))
                final_host = await host.wait_stage(index, "results", args.question_seconds + args.timeout)
                async def final_players():
                    while any(p.observation(index).final is None and not p.disconnected for p in peers):
                        await asyncio.sleep(.02)
                try:
                    await asyncio.wait_for(final_players(), args.timeout)
                except asyncio.TimeoutError:
                    round_result["result_delivery_timeout"] = True
                obs = [p.observation(index) for p in peers]
                ack = distribution([(o.ack_at - o.sent_at) * 1000 for o in obs if o.sent_at is not None and o.ack_at is not None])
                sent = [o.sent_at for o in obs if o.sent_at is not None]
                ready = [o.ready_at for o in obs if o.ready_at is not None]
                errors = Counter(e for o in obs for e in o.errors)
                points = [(o.final or {}).get("answer", {}).get("points", 0) for o in obs]
                accepted = final_host["received"]
                results_received = sum(o.final is not None for o in obs)
                passed = (accepted == count and ack["samples"] == count and results_received == count
                          and ack["p95"] <= args.p95_ms and not errors and not any(p.disconnected for p in peers))
                round_result.update({"status": "PASS" if passed else "FAIL", "answers_accepted_server": accepted,
                                     "answers_missing_server": count - accepted, "results_received": results_received,
                                     "ack_ms": ack, "answer_errors": dict(errors),
                                     "send_span_ms": round((max(sent) - min(sent)) * 1000, 2) if sent else None,
                                     "question_delivery_span_ms": round((max(ready) - min(ready)) * 1000, 2) if ready else None,
                                     "generator_schedule_lag_ms": distribution([o.schedule_lag_ms for o in obs]),
                                     "question_points_min": min(points), "question_points_max": max(points),
                                     "messages_received": sum(p.messages for p in peers + [host]) - before_messages,
                                     "uncompressed_json_MiB": round((sum(p.json_bytes for p in peers + [host]) - before_bytes) / 1048576, 3),
                                     "unexpected_disconnects": sum(p.disconnected for p in peers)})
                log(f"Round {index + 1}/{args.rounds} {round_result['type']}: accepted={accepted}/{count}, "
                    f"ack p95={ack['p95']} ms, errors={dict(errors)}, {round_result['status']}")
                self.save()
            await host.ws.send_json({"action": "leaderboard"})
            await host.wait_stage(args.rounds - 1, "leaderboard", args.timeout)
            await host.ws.send_json({"action": "next"})
            await host.wait_stage(args.rounds - 1, "podium", args.timeout)
            case["status"] = "PASS" if all(r["status"] == "PASS" for r in case["rounds"]) else "FAIL"
        except asyncio.CancelledError:
            case["status"] = "INTERRUPTED"
            raise
        except Exception as error:
            case["status"] = "ERROR"
            case["error"] = type(error).__name__ + ": " + str(error)[:300]
            log(case["error"])
        finally:
            stop.set()
            await monitor
            case["health_ms"] = distribution(case.pop("_health"))
            case["generator_loop_lag_ms"] = distribution(case.pop("_lag"))
            case["generator_cpu_s"] = round(time.process_time() - cpu_started, 3)
            case["elapsed_before_cleanup_s"] = round(time.perf_counter() - wall_started, 3)
            case["unexpected_disconnects"] = sum(p.disconnected for p in peers)
            for p in peers + ([host] if host else []):
                p.expected_close = True
            if host and host.credentials and not host.ws.closed:
                try:
                    await host.ws.send_json({"action": "close"})
                    stage_index = host.state["index"] if host.state else -1
                    await host.wait_stage(stage_index, "closed", min(args.timeout, 15))
                except Exception as error:
                    case["cleanup_errors"].append("room_close: " + type(error).__name__)
            async def close(p):
                try:
                    await asyncio.wait_for(p.ws.close(), 5)
                except Exception:
                    pass
                p.task.cancel()
                await asyncio.gather(p.task, return_exceptions=True)
            await asyncio.gather(*(close(p) for p in peers + ([host] if host else [])))
            if quiz_id:
                try:
                    await self.api("DELETE", "/api/quizzes/" + quiz_id, authenticated=True)
                except Exception as error:
                    case["cleanup_errors"].append("quiz_delete: " + str(error)[:150])
            self.save()
        return case

    async def run(self):
        context = ssl.create_default_context(cafile=self.args.ca_file)
        connector = aiohttp.TCPConnector(limit=0, ssl=context)
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=self.args.timeout),
                                         cookie_jar=aiohttp.DummyCookieJar(), trust_env=False) as session:
            self.http = session
            await self.api("GET", "/health")
            config = await self.api("GET", "/api/config")
            self.report["server_config"] = config
            if max(self.args.levels) > config["maxPlayers"]:
                raise TestFailure(f"Requested {max(self.args.levels)} players but server MAX_PLAYERS={config['maxPlayers']}")
            auth = await self.api("POST", "/api/login", {"password": self.password})
            self.token = auth["token"]
            self.password = None
            for i, count in enumerate(self.args.levels):
                if i:
                    log(f"Cooldown {self.args.cooldown:g}s before next level (v3.0 per-IP connection limit)")
                    await asyncio.sleep(self.args.cooldown)
                case = await self.case(count)
                if self.args.stop_on_fail and case["status"] != "PASS":
                    break
        self.report["status"] = "PASS" if self.report["cases"] and all(c["status"] == "PASS" for c in self.report["cases"]) else "FAIL"
        self.save()
        log(f"Overall {self.report['status']}; report: {self.args.output}")
        return 0 if self.report["status"] == "PASS" else 1


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--url", required=True, help="App URL, e.g. https://quiz.example.org (use the final URL after redirects)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--players", type=int, default=200, help="Number of players in one room")
    group.add_argument("--levels", help="Comma-separated levels, e.g. 50,100,200; separate room per level")
    p.add_argument("--rounds", type=int, default=5, help="Alternating MCQ and open-ended questions")
    p.add_argument("--question-seconds", type=int, default=20)
    p.add_argument("--ramp-seconds", type=float, default=20, help="Spread player joins across this interval")
    p.add_argument("--join-concurrency", type=int, default=10)
    p.add_argument("--think-seconds", type=float, default=1, help="Wait after all players receive the question")
    p.add_argument("--answer-spread", type=float, default=0, help="0=simultaneous burst; otherwise random delay within this many seconds")
    p.add_argument("--cooldown", type=float, default=65, help="Pause between levels; avoids accumulating the 300/IP/min connection quota")
    p.add_argument("--timeout", type=float, default=45, help="Timeout for HTTP/join/state waits")
    p.add_argument("--p95-ms", type=float, default=1000, help="Proposed acceptance threshold for answer acknowledgement p95")
    p.add_argument("--compression", choices=["on", "off"], default="on")
    p.add_argument("--ca-file", help="Optional CA certificate PEM for an internal HTTPS certificate")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--stop-on-fail", action="store_true")
    p.add_argument("--output", default="results/quizspark-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    args = p.parse_args()
    try:
        args.levels = [int(x) for x in args.levels.split(",")] if args.levels else [args.players]
    except ValueError:
        p.error("--levels must contain integers separated by commas")
    parts = urlsplit(args.url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        p.error("--url must be an http(s) app URL without credentials, query or fragment")
    args.url = args.url.rstrip("/")
    if not args.levels or min(args.levels) < 1 or max(args.levels) > 5000:
        p.error("Player count must be between 1 and 5000, and no higher than server MAX_PLAYERS")
    if not 1 <= args.rounds <= 100 or not 5 <= args.question_seconds <= 300:
        p.error("Use 1–100 rounds and 5–300 seconds per question")
    if args.join_concurrency < 1 or args.timeout <= 0 or args.p95_ms <= 0:
        p.error("Concurrency, timeout and p95 threshold must be positive")
    if min(args.ramp_seconds, args.think_seconds, args.answer_spread, args.cooldown) < 0:
        p.error("Delays cannot be negative")
    if args.think_seconds + args.answer_spread >= args.question_seconds:
        p.error("think-seconds + answer-spread must be less than question-seconds")
    return args


def main():
    args = parse_args()
    password = os.environ.get("QUIZSPARK_ADMIN_PASSWORD") or getpass.getpass("QuizSpark host password: ")
    if not password:
        raise SystemExit("A host password is required")
    runner = Runner(args, password)
    try:
        code = asyncio.run(runner.run())
    except KeyboardInterrupt:
        runner.report["status"] = "INTERRUPTED"
        runner.save()
        print("Interrupted; partial report saved to " + args.output, file=sys.stderr)
        code = 130
    except Exception as error:
        runner.report["status"] = "ERROR"
        runner.report["error"] = type(error).__name__ + ": " + str(error)[:300]
        runner.save()
        print(runner.report["error"], file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
