"""Integration tests against actual HTTP and WebSocket connections."""
import asyncio
import base64
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from aiohttp import FormData, WSMsgType
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from server import create_app


def sample():
    return {"title": "Integration quiz", "category": "Testing", "questions": [
        {"type": "mcq", "text": "2 + 2?", "options": ["2", "3", "4", "5"], "correct": 2, "time": 5,
         "explanationText": "Add two and two."},
        {"type": "open", "text": "Gold symbol?", "openAnswers": ["Au"], "time": 5,
         "explanationText": "Aurum."},
    ]}


async def receive(ws, predicate, timeout=8):
    async with asyncio.timeout(timeout):
        while True:
            message = await ws.receive()
            if message.type != WSMsgType.TEXT:
                raise AssertionError(f"Unexpected WS message: {message}")
            data = json.loads(message.data)
            if predicate(data):
                return data


async def state(ws, stage, predicate=lambda s: True):
    return (await receive(ws, lambda d: d.get("type") == "state" and d["state"]["stage"] == stage and predicate(d["state"])))["state"]


class Integration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        await self.start()

    async def start(self):
        self.client = TestClient(TestServer(create_app(self.temp.name, "test-password-only")))
        await self.client.start_server()
        result = await self.client.post("/api/login", json={"password": "test-password-only"})
        self.token = (await result.json())["token"]
        self.auth = {"Authorization": "Bearer " + self.token}

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def create(self, quiz=None):
        response = await self.client.post("/api/quizzes", json=quiz or sample(), headers=self.auth)
        self.assertEqual(response.status, 201, await response.text())
        return await response.json()

    async def host(self, quiz):
        ws = await self.client.ws_connect("/ws")
        await ws.send_json({"type": "create", "adminToken": self.token, "quizId": quiz["id"]})
        connected = await receive(ws, lambda d: d.get("type") == "connected")
        await state(ws, "lobby")
        return ws, connected

    async def player(self, pin, name):
        ws = await self.client.ws_connect("/ws")
        await ws.send_json({"type": "join", "pin": pin, "name": name, "avatar": "🦊"})
        connected = await receive(ws, lambda d: d.get("type") == "connected")
        await state(ws, "lobby")
        return ws, connected

    async def test_quiz_images_and_imports_survive_server_recreation(self):
        image = io.BytesIO()
        Image.new("RGB", (4, 4), "purple").save(image, format="PNG")
        image_bytes = image.getvalue()
        upload = FormData()
        upload.add_field("file", image_bytes, filename="../../evil.png", content_type="image/png")
        response = await self.client.post("/api/uploads", data=upload, headers=self.auth)
        self.assertEqual(response.status, 201)
        url = (await response.json())["url"]
        q = sample()
        q["questions"][0]["image"] = url
        q["questions"][1]["explanationImage"] = "data:image/png;base64," + base64.b64encode(image_bytes).decode()
        quiz = await self.create(q)
        exported = await (await self.client.get(f'/api/quizzes/{quiz["id"]}/export', headers=self.auth)).json()
        self.assertTrue(exported["questions"][0]["image"].startswith("data:image/png;base64,"))
        raw = json.dumps(exported).encode()
        form = FormData()
        form.add_field("file", raw, filename="portable.json", content_type="application/json")
        result = await self.client.post("/api/import", data=form, headers=self.auth)
        self.assertEqual(result.status, 201, await result.text())
        self.assertEqual(len(list((Path(self.temp.name) / "uploads").iterdir())), 1)
        self.assertEqual(next((Path(self.temp.name) / "imports").iterdir()).read_bytes(), raw)
        old_token = self.token
        await self.client.close()
        await self.start()
        self.assertEqual((await self.client.get("/api/quizzes", headers={"Authorization": "Bearer " + old_token})).status, 401)
        quizzes = await (await self.client.get("/api/quizzes", headers=self.auth)).json()
        restored = next(q for q in quizzes if q["id"] == quiz["id"])
        self.assertEqual(restored["questions"][0]["image"], url)
        response = await self.client.get(url)
        self.assertEqual(await response.read(), image_bytes)
        self.assertEqual(response.headers["Content-Type"], "image/png")

    async def test_complete_multiplayer_game_and_reconnect(self):
        quiz = await self.create()
        host, credentials = await self.host(quiz)
        pin = credentials["pin"]
        first, first_credentials = await self.player(pin, "หนุ่ม")
        second, _ = await self.player(pin, "Player Two")
        await state(host, "lobby", lambda s: len(s["players"]) == 2)
        await host.send_json({"action": "start"})
        before = await state(first, "question")
        self.assertNotIn("correct", before["question"])
        self.assertNotIn("explanationText", before["question"])
        self.assertNotIn("responses", before)
        await first.send_json({"type": "answer", "value": 2, "index": 0})
        waiting = await state(first, "question", lambda s: s["me"]["answered"])
        self.assertEqual(waiting["me"]["score"], 0)
        self.assertNotIn("answer", waiting["me"])
        await first.send_json({"type": "answer", "value": 1, "index": 0})
        duplicate = await receive(first, lambda d: d.get("type") == "error")
        self.assertEqual(duplicate["code"], "already_answered")
        await second.send_json({"action": "reveal"})
        denied = await receive(second, lambda d: d.get("type") == "error")
        self.assertEqual(denied["code"], "invalid_action")
        await second.send_json({"type": "answer", "value": 0, "index": 0})
        result = await state(first, "results")
        self.assertTrue(result["me"]["answer"]["correct"])
        self.assertGreaterEqual(result["me"]["score"], 500)
        self.assertLessEqual(result["me"]["score"], 1000)
        self.assertEqual(result["me"]["streak"], 1)
        await first.close()
        first = await self.client.ws_connect("/ws")
        await first.send_json({"type": "resume", "pin": pin, "token": first_credentials["token"]})
        await receive(first, lambda d: d.get("type") == "connected")
        resumed = await state(first, "results")
        self.assertEqual(resumed["me"]["score"], result["me"]["score"])
        # The host can reconnect as well without granting host access to players.
        await host.close()
        host = await self.client.ws_connect("/ws")
        await host.send_json({"type": "resume", "pin": pin, "token": credentials["token"]})
        await receive(host, lambda d: d.get("type") == "connected")
        await state(host, "results")
        await host.send_json({"action": "leaderboard"})
        await state(first, "leaderboard")
        await host.send_json({"action": "next"})
        current = await state(first, "question")
        self.assertEqual(current["index"], 1)
        self.assertNotIn("openAnswers", current["question"])
        await first.send_json({"type": "answer", "value": "  ａｕ  ", "index": 1})
        await second.send_json({"type": "answer", "value": "Ag", "index": 1})
        final = await state(first, "results")
        self.assertTrue(final["me"]["answer"]["correct"])
        self.assertEqual(final["me"]["streak"], 2)
        wrong = await state(second, "results", lambda s: s["index"] == 1)
        self.assertEqual(wrong["me"]["score"], 0)
        await host.send_json({"action": "leaderboard"})
        await state(first, "leaderboard")
        await host.send_json({"action": "next"})
        podium = await state(first, "podium")
        self.assertEqual(podium["players"][0]["name"], "หนุ่ม")
        self.assertEqual(len(podium["players"]), 2)

    async def test_deadline_enforced_and_late_answer_rejected(self):
        quiz = await self.create()
        host, session = await self.host(quiz)
        player, _ = await self.player(session["pin"], "Late Player")
        await host.send_json({"action": "start"})
        await state(player, "question")
        result = await state(player, "results")
        self.assertEqual(result["received"], 0)
        self.assertEqual(result["me"]["score"], 0)
        await player.send_json({"type": "answer", "value": 2, "index": 0})
        error = await receive(player, lambda d: d.get("type") == "error")
        self.assertEqual(error["code"], "round_closed")

    async def test_slow_receiver_does_not_block_other_players(self):
        quiz = await self.create()
        host, credentials = await self.host(quiz)
        first, _ = await self.player(credentials["pin"], "Fast One")
        second, _ = await self.player(credentials["pin"], "Fast Two")
        slow, _ = await self.player(credentials["pin"], "Slow Receiver")
        await host.send_json({"action": "start"})
        await asyncio.gather(*(state(ws, "question") for ws in (host, first, second, slow)))
        service = next(value for value in self.client.server.app.values() if hasattr(value, "rooms"))
        room = service.rooms[credentials["pin"]]
        socket = next(p["ws"] for p in room.players.values() if p["name"] == "Slow Receiver")
        original = socket.send_str
        blocked, release = asyncio.Event(), asyncio.Event()
        async def delayed_send(payload):
            blocked.set()
            await release.wait()
            await original(payload)
        socket.send_str = delayed_send
        try:
            # Inject an indefinitely stalled network write for one real client.
            room.broadcast(immediate=True)
            await asyncio.wait_for(blocked.wait(), 1)
            async with asyncio.timeout(1):
                await first.send_json({"type": "answer", "index": 0, "value": 2})
                ack = await state(first, "question", lambda s: s["me"]["answered"])
                self.assertNotIn("correct", ack["question"])
                await second.send_json({"type": "answer", "index": 0, "value": 2})
                await slow.send_json({"type": "answer", "index": 0, "value": 2})
                result = await state(host, "results")
                self.assertEqual(result["received"], 3)
                self.assertEqual(len(result["responses"]), 3)
                self.assertTrue((await state(second, "results"))["me"]["answer"]["correct"])
        finally:
            release.set()
            socket.send_str = original

    async def test_score_uses_receipt_time_before_room_lock(self):
        quiz = await self.create()
        host, credentials = await self.host(quiz)
        first, _ = await self.player(credentials["pin"], "Queued Answer")
        second, _ = await self.player(credentials["pin"], "Other Answer")
        await host.send_json({"action": "start"})
        await asyncio.gather(state(first, "question"), state(second, "question"))
        service = next(value for value in self.client.server.app.values() if hasattr(value, "rooms"))
        room = service.rooms[credentials["pin"]]
        async with room.lock:
            await first.send_json({"type": "answer", "index": 0, "value": 2})
            await asyncio.sleep(.4)
            released_at = time.monotonic()
        await state(first, "question", lambda s: s["me"]["answered"])
        await second.send_json({"type": "answer", "index": 0, "value": 2})
        result = await state(first, "results")
        score_if_delayed = 1000 - (released_at - room.started) * 100
        self.assertGreater(result["me"]["answer"]["points"], score_if_delayed + 20)

    async def test_live_resume_and_kick_deliver_control_before_close(self):
        quiz = await self.create()
        host, credentials = await self.host(quiz)
        original, player_credentials = await self.player(credentials["pin"], "Reconnecting Player")
        replacement = await self.client.ws_connect("/ws")
        await replacement.send_json({"type": "resume", "pin": credentials["pin"], "token": player_credentials["token"]})
        await receive(replacement, lambda d: d.get("type") == "connected")
        lobby = await state(replacement, "lobby")
        async with asyncio.timeout(1):
            while (await original.receive()).type == WSMsgType.TEXT:
                pass
        self.assertEqual(original.close_code, 4001)
        await host.send_json({"action": "kick", "id": lobby["me"]["id"]})
        await receive(replacement, lambda d: d.get("type") == "kicked")
        async with asyncio.timeout(1):
            while (await replacement.receive()).type == WSMsgType.TEXT:
                pass
        self.assertEqual(replacement.close_code, 1000)

    async def test_unauthorized_upload_invalid_content_and_quiz_validation(self):
        self.assertEqual((await self.client.get("/api/quizzes")).status, 401)
        self.assertEqual((await self.client.post("/api/quizzes", json=sample())).status, 401)
        self.assertEqual((await self.client.post("/api/uploads", data=b"anything")).status, 401)
        svg = FormData()
        svg.add_field("file", b'<svg onload="alert(1)"></svg>', filename="fake.png", content_type="image/png")
        result = await self.client.post("/api/uploads", data=svg, headers=self.auth)
        self.assertEqual(result.status, 400)
        self.assertEqual((await result.json())["error"], "unsupported_image")
        oversized = FormData()
        oversized.add_field("file", io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), filename="large.png", content_type="image/png")
        result = await self.client.post("/api/uploads", data=oversized, headers=self.auth)
        self.assertEqual(result.status, 413)
        for value in [-1, 4, True, "2"]:
            q = sample()
            q["questions"][0]["correct"] = value
            self.assertEqual((await self.client.post("/api/quizzes", json=q, headers=self.auth)).status, 400)
        q = sample()
        q["questions"][0]["image"] = 'javascript:alert(1)'
        self.assertEqual((await self.client.post("/api/quizzes", json=q, headers=self.auth)).status, 400)
        # Private files are not served by the public upload handler.
        self.assertEqual((await self.client.get("/uploads/admin-password")).status, 404)
        self.assertEqual((await self.client.get("/data/quizspark.sqlite3")).status, 404)

    async def test_original_import_rejected_without_saving_and_deleted_quiz_stays_deleted(self):
        bad = FormData()
        bad.add_field("file", b'{"title":"no questions"}', filename="bad.json", content_type="application/json")
        self.assertEqual((await self.client.post("/api/import", data=bad, headers=self.auth)).status, 400)
        self.assertFalse(list((Path(self.temp.name) / "imports").iterdir()))
        quizzes = await (await self.client.get("/api/quizzes", headers=self.auth)).json()
        for q in quizzes:
            self.assertEqual((await self.client.delete('/api/quizzes/' + q["id"], headers=self.auth)).status, 200)
        await self.client.close()
        await self.start()
        self.assertEqual(await (await self.client.get("/api/quizzes", headers=self.auth)).json(), [])


if __name__ == "__main__":
    unittest.main()
