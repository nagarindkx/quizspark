"""QuizSpark: one-process HTTP/WebSocket server with durable quizzes and uploads."""
import asyncio
import base64
import copy
import hashlib
import hmac
import io
import json
import logging
import math
import os
import random
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
import warnings
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
AVATARS = ["🦊", "🐼", "🐯", "🐸", "🐙", "🦄", "🐨", "🦁", "🐧", "🐳", "🤖", "🚀"]
EXTENSIONS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}
MIMES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
Image.MAX_IMAGE_PIXELS = 25_000_000
log = logging.getLogger("quizspark")


class Invalid(Exception):
    def __init__(self, code="invalid", status=400):
        self.code, self.status = code, status


def text_value(value, maximum, required=True):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise Invalid("invalid_quiz")
    return value.strip()


def normalized(value):
    return unicodedata.normalize("NFKC", value).strip().casefold()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Invalid("invalid_quiz")
    return value


def atomic_bytes(path, body):
    temporary = path.with_suffix(path.suffix + ".tmp-" + secrets.token_hex(4))
    try:
        with temporary.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class Storage:
    def __init__(self, directory, max_upload):
        self.directory = Path(directory)
        self.uploads = self.directory / "uploads"
        self.imports = self.directory / "imports"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.imports.mkdir(parents=True, exist_ok=True)
        self.max_upload = max_upload
        self.db = sqlite3.connect(self.directory / "quizspark.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("CREATE TABLE IF NOT EXISTS quizzes (id TEXT PRIMARY KEY, document TEXT NOT NULL, updated REAL NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        # The marker prevents deleted sample quizzes from returning on restart.
        if not self.db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
            for quiz in json.loads((ROOT / "defaults.json").read_text()):
                self.save(self.validate(quiz))
            self.db.execute("INSERT INTO settings VALUES ('seeded','1')")
            self.db.commit()

    def image(self, body):
        if not body or len(body) > self.max_upload:
            raise Invalid("file_too_large", 413)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(body)) as image:
                    extension = EXTENSIONS.get(image.format)
                    if not extension:
                        raise Invalid("unsupported_image")
                    image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise Invalid("unsupported_image") from None
        # Content-addressed names deduplicate repeated imports and never trust filenames.
        name = hashlib.sha256(body).hexdigest() + "." + extension
        path = self.uploads / name
        if not path.exists():
            atomic_bytes(path, body)
        return "/uploads/" + name

    def image_reference(self, value):
        if not value:
            return ""
        if not isinstance(value, str):
            raise Invalid("invalid_image")
        if value.startswith("data:image/"):
            if len(value) > self.max_upload * 4 // 3 + 256:
                raise Invalid("file_too_large", 413)
            try:
                header, encoded = value.split(",", 1)
                if not header.endswith(";base64"):
                    raise ValueError()
                return self.image(base64.b64decode(encoded, validate=True))
            except (ValueError, TypeError):
                raise Invalid("invalid_image") from None
        if re.fullmatch(r"/uploads/[a-f0-9]{64}\.(png|jpg|webp|gif)", value):
            if not (self.uploads / value.rsplit("/", 1)[1]).is_file():
                raise Invalid("missing_image")
            return value
        parts = urlsplit(value)
        if len(value) <= 2048 and parts.scheme in ("http", "https") and parts.netloc:
            return value
        raise Invalid("invalid_image")

    def validate(self, data, forced_id=None):
        if not isinstance(data, dict):
            raise Invalid("invalid_quiz")
        questions = data.get("questions")
        if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
            raise Invalid("invalid_quiz")
        result = {"id": forced_id or str(uuid.uuid4()), "title": text_value(data.get("title"), 160),
                  "category": text_value(data.get("category", ""), 100, False), "questions": []}
        for q in questions:
            if not isinstance(q, dict) or q.get("type") not in ("mcq", "open"):
                raise Invalid("invalid_quiz")
            clean = {"type": q["type"], "text": text_value(q.get("text"), 2000),
                     "time": integer(q.get("time", 20), 5, 300),
                     "emoji": text_value(q.get("emoji", "💡"), 32, False),
                     "explanationText": text_value(q.get("explanationText", ""), 5000, False)}
            if q["type"] == "mcq":
                options = q.get("options")
                if not isinstance(options, list) or len(options) != 4:
                    raise Invalid("invalid_quiz")
                clean["options"] = [text_value(o, 500) for o in options]
                clean["correct"] = integer(q.get("correct"), 0, 3)
            else:
                answers = q.get("openAnswers")
                if not isinstance(answers, list) or not 1 <= len(answers) <= 50:
                    raise Invalid("invalid_quiz")
                clean["openAnswers"] = [text_value(a, 200) for a in answers]
            for field in ("image", "explanationImage"):
                clean[field] = self.image_reference(q.get(field, ""))
            result["questions"].append(clean)
        return result

    def save(self, quiz):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO quizzes VALUES (?,?,?)", (quiz["id"], json.dumps(quiz, ensure_ascii=False), time.time()))
        return quiz

    def get(self, quiz_id):
        row = self.db.execute("SELECT document FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
        if not row:
            raise Invalid("quiz_missing", 404)
        return json.loads(row[0])

    def export(self, quiz_id):
        quiz = self.get(quiz_id)
        for q in quiz["questions"]:
            for field in ("image", "explanationImage"):
                if q[field].startswith("/uploads/"):
                    path = self.uploads / q[field].rsplit("/", 1)[1]
                    mime = MIMES[path.suffix[1:]]
                    q[field] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
        return quiz


class Room:
    def __init__(self, service, pin, quiz):
        self.service, self.pin, self.quiz = service, pin, copy.deepcopy(quiz)
        self.host_token = secrets.token_urlsafe(32)
        self.host = None
        self.players = {}
        self.stage, self.index = "lobby", -1
        self.answers = {}
        self.started, self.deadline = 0, 0
        self.touched = time.monotonic()
        self.lock = asyncio.Lock()
        self.tasks = set()

    def task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def cancel_tasks(self):
        for task in tuple(self.tasks):
            if task is not asyncio.current_task():
                task.cancel()

    def ranking(self):
        ranked = sorted(self.players.values(), key=lambda p: (-p["score"], p["order"]))
        return [{"id": p["id"], "name": p["name"], "avatar": p["avatar"], "score": p["score"],
                 "streak": p["streak"], "rank": i + 1, "online": p["bot"] or (p["ws"] is not None and not p["ws"].closed),
                 "bot": p["bot"]} for i, p in enumerate(ranked)]

    def snapshot(self, player_id=None):
        ranking = self.ranking()
        state = {"pin": self.pin, "title": self.quiz["title"], "stage": self.stage, "index": self.index,
                 "total": len(self.quiz["questions"]), "players": ranking, "received": len(self.answers),
                 "deadline": self.deadline, "serverNow": time.time() * 1000,
                 "hostOnline": self.host is not None and not self.host.closed}
        if self.index >= 0:
            q = self.quiz["questions"][self.index]
            # Never send solutions or explanations until the round is over.
            state["question"] = {key: q[key] for key in ("type", "text", "time", "image", "emoji")}
            if q["type"] == "mcq":
                state["question"]["options"] = q["options"]
            if self.stage in ("results", "leaderboard", "podium"):
                state["question"] = q
                if player_id is None:
                    state["responses"] = [{"id": p, "name": self.players[p]["name"], **a} for p, a in self.answers.items()]
        if player_id is not None:
            me = next(p for p in ranking if p["id"] == player_id)
            me["answered"] = player_id in self.answers
            if self.stage in ("results", "leaderboard", "podium"):
                me["answer"] = self.answers.get(player_id, {"correct": False, "points": 0, "value": None})
            state["me"] = me
        return {"type": "state", "state": state}

    async def broadcast(self):
        recipients = [(self.host, None)] + [(p["ws"], p["id"]) for p in self.players.values() if not p["bot"]]
        sends = [self.service.send(ws, self.snapshot(pid)) for ws, pid in recipients if ws is not None and not ws.closed]
        if sends:
            await asyncio.gather(*sends)

    def add_player(self, name, avatar, bot=False):
        if self.stage != "lobby":
            raise Invalid("already_started")
        if len(self.players) >= self.service.max_players:
            raise Invalid("room_full")
        name = text_value(name, 24)
        if any(normalized(p["name"]) == normalized(name) for p in self.players.values()):
            raise Invalid("name_taken")
        player = {"id": str(uuid.uuid4()), "token": secrets.token_urlsafe(32), "name": name,
                  "avatar": avatar if avatar in AVATARS else AVATARS[0], "score": 0, "streak": 0,
                  "bot": bot, "ws": None, "order": time.monotonic()}
        self.players[player["id"]] = player
        return player

    async def start_question(self):
        self.cancel_tasks()
        self.index += 1
        self.stage, self.answers = "question", {}
        duration = self.quiz["questions"][self.index]["time"]
        self.started = time.monotonic()
        self.deadline = time.time() * 1000 + duration * 1000
        self.task(self.timeout(self.index, duration))
        for p in self.players.values():
            if p["bot"]:
                self.task(self.bot_answer(p["id"], self.index, random.uniform(1, duration * .9)))

    async def timeout(self, index, duration):
        await asyncio.sleep(duration)
        async with self.lock:
            if self.stage == "question" and self.index == index:
                self.reveal()
                await self.broadcast()

    async def bot_answer(self, player_id, index, delay):
        await asyncio.sleep(delay)
        async with self.lock:
            if self.stage != "question" or self.index != index:
                return
            q = self.quiz["questions"][self.index]
            value = (q["correct"] if random.random() < .7 else random.randrange(4)) if q["type"] == "mcq" else (q["openAnswers"][0] if random.random() < .7 else "?")
            try:
                self.answer(player_id, value, index)
            except Invalid:
                # A busy event loop may resume a bot just after the deadline.
                return
            await self.broadcast()

    def answer(self, player_id, value, index):
        if self.stage != "question" or index != self.index:
            raise Invalid("round_closed")
        if player_id in self.answers:
            raise Invalid("already_answered")
        q = self.quiz["questions"][self.index]
        elapsed = time.monotonic() - self.started
        if elapsed >= q["time"]:
            raise Invalid("round_closed")
        if q["type"] == "mcq":
            integer(value, 0, 3)
            correct = value == q["correct"]
        else:
            value = text_value(value, 200)
            correct = normalized(value) in {normalized(a) for a in q["openAnswers"]}
        points = math.floor(1000 * (1 - elapsed / (q["time"] * 2)) + .5) if correct else 0
        self.answers[player_id] = {"value": value, "correct": correct, "points": points}
        if len(self.answers) == len(self.players):
            self.reveal()

    def reveal(self):
        if self.stage != "question":
            return
        self.stage = "results"
        self.cancel_tasks()
        for pid, player in self.players.items():
            answer = self.answers.get(pid, {})
            player["score"] += answer.get("points", 0)
            player["streak"] = player["streak"] + 1 if answer.get("correct") else 0

    async def command(self, message):
        action = message.get("action")
        self.touched = time.monotonic()
        if action == "start" and self.stage == "lobby" and self.players:
            await self.start_question()
        elif action == "reveal" and self.stage == "question":
            self.reveal()
        elif action == "leaderboard" and self.stage == "results":
            self.stage = "leaderboard"
        elif action == "next" and self.stage == "leaderboard":
            if self.index + 1 == len(self.quiz["questions"]):
                self.stage = "podium"
            else:
                await self.start_question()
        elif action == "add_bot" and self.stage == "lobby":
            self.add_player("Bot " + secrets.token_hex(2), random.choice(AVATARS), True)
        elif action == "kick" and self.stage == "lobby":
            player = self.players.pop(message.get("id"), None)
            if player and player["ws"] is not None:
                await self.service.send(player["ws"], {"type": "kicked"})
                await player["ws"].close()
        elif action == "close":
            self.stage = "closed"
            self.cancel_tasks()
        else:
            raise Invalid("invalid_action")


class Service:
    def __init__(self, directory, password=None):
        self.max_upload = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
        self.max_import = int(os.getenv("MAX_IMPORT_MB", "50")) * 1024 * 1024
        self.max_players = int(os.getenv("MAX_PLAYERS", "200"))
        self.storage = Storage(directory, self.max_upload)
        credential = self.storage.directory / "admin-password"
        if password:
            self.password = password
        elif credential.exists():
            self.password = credential.read_text().strip()
        else:
            self.password = secrets.token_urlsafe(24)
            atomic_bytes(credential, (self.password + "\n").encode())
            credential.chmod(0o600)
            log.warning("Admin password created in %s (use docker compose exec quizspark cat /app/data/admin-password)", credential)
        self.sessions, self.rooms = {}, {}
        self.limits = defaultdict(deque)
        self.sockets = set()

    def rate(self, key, count=30, window=60):
        now = time.monotonic()
        queue = self.limits[key]
        while queue and queue[0] < now - window:
            queue.popleft()
        if len(queue) >= count:
            raise Invalid("rate_limit", 429)
        queue.append(now)

    def auth(self, token):
        if not isinstance(token, str) or self.sessions.get(token, 0) < time.monotonic():
            raise Invalid("login_required", 401)

    def authorize(self, request):
        self.auth(request.headers.get("Authorization", "").removeprefix("Bearer "))

    async def send(self, ws, value):
        try:
            async with asyncio.timeout(3):
                await ws.send_json(value)
        except (ConnectionError, RuntimeError, TimeoutError):
            pass

    async def health(self, request):
        self.storage.db.execute("SELECT 1").fetchone()
        return web.json_response({"status": "ok", "version": "3.0-docker"})

    async def login(self, request):
        self.rate(("login", request.remote), 10)
        data = await request.json()
        value = data.get("password", "") if isinstance(data, dict) else ""
        if not isinstance(value, str) or not hmac.compare_digest(value.encode(), self.password.encode()):
            raise Invalid("wrong_password", 401)
        token = secrets.token_urlsafe(32)
        self.sessions[token] = time.monotonic() + 12 * 3600
        return web.json_response({"token": token})

    async def quizzes(self, request):
        self.authorize(request)
        if request.method == "GET":
            rows = self.storage.db.execute("SELECT document FROM quizzes ORDER BY updated DESC").fetchall()
            return web.json_response([json.loads(row[0]) for row in rows])
        quiz = self.storage.validate(await request.json())
        return web.json_response(self.storage.save(quiz), status=201)

    async def quiz(self, request):
        self.authorize(request)
        quiz_id = request.match_info["id"]
        self.storage.get(quiz_id)
        if request.method == "DELETE":
            with self.storage.db:
                self.storage.db.execute("DELETE FROM quizzes WHERE id=?", (quiz_id,))
            return web.json_response({"ok": True})
        quiz = self.storage.validate(await request.json(), quiz_id)
        return web.json_response(self.storage.save(quiz))

    async def export(self, request):
        self.authorize(request)
        return web.json_response(self.storage.export(request.match_info["id"]),
                                 headers={"Content-Disposition": 'attachment; filename="quizspark-export.json"'})

    async def read_file(self, request, limit):
        if not request.content_type.startswith("multipart/"):
            raise Invalid("invalid_upload")
        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != "file" or not part.filename:
            raise Invalid("invalid_upload")
        body = bytearray()
        while True:
            chunk = await part.read_chunk(64 * 1024)
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > limit:
                raise Invalid("file_too_large", 413)
        return bytes(body)

    async def upload(self, request):
        self.authorize(request)
        body = await self.read_file(request, self.max_upload)
        url = await asyncio.to_thread(self.storage.image, body)
        return web.json_response({"url": url, "size": len(body)}, status=201)

    async def import_quizzes(self, request):
        self.authorize(request)
        body = await self.read_file(request, self.max_import)
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise Invalid("invalid_json") from None
        items = data if isinstance(data, list) else [data]
        if not 1 <= len(items) <= 100:
            raise Invalid("invalid_quiz")
        validated = [self.storage.validate(item) for item in items]
        # Keep the original imported file, including embedded images, inside the data volume.
        atomic_bytes(self.storage.imports / (str(uuid.uuid4()) + ".json"), body)
        with self.storage.db:
            for quiz in validated:
                self.storage.db.execute("INSERT INTO quizzes VALUES (?,?,?)", (quiz["id"], json.dumps(quiz, ensure_ascii=False), time.time()))
        return web.json_response({"count": len(validated)}, status=201)

    async def uploaded_file(self, request):
        name = request.match_info["name"]
        if not re.fullmatch(r"[a-f0-9]{64}\.(png|jpg|webp|gif)", name):
            raise web.HTTPNotFound()
        path = self.storage.uploads / name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Type": MIMES[path.suffix[1:]], "Cache-Control": "public, max-age=31536000, immutable"})

    async def socket(self, request):
        # Origin checking needs no proxy-specific Host rewrite; reverse proxies preserve Host.
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            raise Invalid("invalid_origin", 403)
        self.rate(("connect", request.remote), 300)
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=16 * 1024)
        await ws.prepare(request)
        self.sockets.add(ws)
        room, player_id, role = None, None, None
        message_times = deque()
        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                try:
                    now = time.monotonic()
                    while message_times and message_times[0] < now - 1:
                        message_times.popleft()
                    if len(message_times) >= 25:
                        raise Invalid("rate_limit", 429)
                    message_times.append(now)
                    data = json.loads(message.data)
                    if not isinstance(data, dict):
                        raise Invalid()
                    if room is None:
                        self.rate(("join", request.remote), 300)
                        operation = data.get("type")
                        if operation == "create":
                            self.auth(data.get("adminToken"))
                            if len(self.rooms) >= 100:
                                raise Invalid("server_full")
                            quiz = self.storage.get(text_value(data.get("quizId"), 100))
                            pin = str(secrets.randbelow(900000) + 100000)
                            while pin in self.rooms:
                                pin = str(secrets.randbelow(900000) + 100000)
                            room = Room(self, pin, quiz)
                            self.rooms[pin] = room
                            room.host, role = ws, "host"
                            token = room.host_token
                        elif operation in ("join", "resume"):
                            pin = text_value(data.get("pin"), 6)
                            candidate = self.rooms.get(pin)
                            if candidate is None or candidate.stage == "closed":
                                raise Invalid("room_missing")
                            async with candidate.lock:
                                if operation == "join":
                                    p = candidate.add_player(data.get("name"), data.get("avatar"))
                                    player_id, token, role = p["id"], p["token"], "player"
                                    p["ws"] = ws
                                else:
                                    token = data.get("token")
                                    if not isinstance(token, str):
                                        raise Invalid("room_missing")
                                    if hmac.compare_digest(token, candidate.host_token):
                                        old, role = candidate.host, "host"
                                        candidate.host = ws
                                    else:
                                        p = next((p for p in candidate.players.values() if hmac.compare_digest(p["token"], token)), None)
                                        if p is None:
                                            raise Invalid("room_missing")
                                        old, player_id, role = p["ws"], p["id"], "player"
                                        p["ws"] = ws
                                    if old is not None and old is not ws:
                                        await old.close(code=4001, message=b"Reconnected elsewhere")
                                room = candidate
                        else:
                            raise Invalid("invalid_action")
                        await self.send(ws, {"type": "connected", "pin": room.pin, "role": role, "token": token})
                        await room.broadcast()
                    else:
                        async with room.lock:
                            if role == "host":
                                if room.host is not ws:
                                    raise Invalid("invalid_action")
                                await room.command(data)
                            elif data.get("type") == "answer":
                                if player_id not in room.players or room.players[player_id]["ws"] is not ws:
                                    raise Invalid("room_missing")
                                room.answer(player_id, data.get("value"), data.get("index"))
                            else:
                                raise Invalid("invalid_action")
                            await room.broadcast()
                except Invalid as error:
                    await self.send(ws, {"type": "error", "code": error.code})
                except (ValueError, TypeError, KeyError):
                    await self.send(ws, {"type": "error", "code": "invalid"})
        finally:
            self.sockets.discard(ws)
            if room:
                if role == "host" and room.host is ws:
                    room.host = None
                elif player_id in room.players and room.players[player_id]["ws"] is ws:
                    room.players[player_id]["ws"] = None
                await room.broadcast()
        return ws

    async def lifecycle(self, app):
        async def cleanup():
            while True:
                await asyncio.sleep(60)
                now = time.monotonic()
                for pin, room in list(self.rooms.items()):
                    ttl = 300 if room.stage == "closed" else 6 * 3600
                    if now - room.touched > ttl:
                        async with room.lock:
                            room.stage = "closed"
                            room.cancel_tasks()
                            await room.broadcast()
                        del self.rooms[pin]
                for key, queue in list(self.limits.items()):
                    if not queue or queue[-1] < now - 60:
                        del self.limits[key]
                self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        task = asyncio.create_task(cleanup())
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for room in self.rooms.values():
            room.cancel_tasks()
        await asyncio.gather(*(ws.close(code=1001, message=b"Server stopping") for ws in tuple(self.sockets)), return_exceptions=True)
        self.storage.db.close()


@web.middleware
async def errors(request, handler):
    try:
        response = await handler(request)
    except Invalid as error:
        response = web.json_response({"error": error.code}, status=error.status)
    except (json.JSONDecodeError, UnicodeDecodeError):
        response = web.json_response({"error": "invalid_json"}, status=400)
    except web.HTTPException as error:
        response = web.json_response({"error": "file_too_large" if error.status == 413 else "http_error"}, status=error.status)
    if not response.prepared:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https: http:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith("/api/") or request.path == "/":
            response.headers["Cache-Control"] = "no-store"
    return response


def create_app(directory=None, password=None):
    service = Service(directory or os.getenv("DATA_DIR", "/app/data"), password or os.getenv("ADMIN_PASSWORD"))
    app = web.Application(middlewares=[errors], client_max_size=service.max_import + 1024 * 1024)
    app[web.AppKey("service", Service)] = service
    app.cleanup_ctx.append(service.lifecycle)

    async def index(request):
        return web.FileResponse(ROOT / "static" / "index.html")

    async def config(request):
        return web.json_response({"maxUploadMB": service.max_upload // 1024 // 1024,
                                  "maxImportMB": service.max_import // 1024 // 1024, "maxPlayers": service.max_players})

    app.add_routes([
        web.get("/", index), web.get("/health", service.health), web.get("/api/config", config),
        web.post("/api/login", service.login), web.get("/api/quizzes", service.quizzes),
        web.post("/api/quizzes", service.quizzes), web.put("/api/quizzes/{id}", service.quiz),
        web.delete("/api/quizzes/{id}", service.quiz), web.get("/api/quizzes/{id}/export", service.export),
        web.post("/api/uploads", service.upload), web.post("/api/import", service.import_quizzes),
        web.get("/uploads/{name}", service.uploaded_file), web.get("/ws", service.socket),
        web.static("/fonts", ROOT / "static" / "fonts"),
    ])
    return app


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    web.run_app(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")), access_log=None)
