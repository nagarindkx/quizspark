# Verification

Verified on 2026-09-22 with Python 3.12, aiohttp 3.13.5, Pillow 12.3.0,
and headless Chromium 153.0.8010.0.

## Passed

- Five HTTP/WebSocket integration tests in `tests/test_app.py`.
- MCQ and open-ended multiplayer rounds, speed-based scoring, streaks, scoreboard and podium.
- Player and host reconnection using the same room/session token.
- Round timeout and rejection of late or duplicate answers.
- Player clients cannot issue host commands; solutions are withheld during a question.
- Quiz management and uploads require host authentication.
- Genuine image validation, upload size limit, unsafe image URLs and private-file access.
- Uploaded image bytes and quiz references survive closing and recreating the server against the same data directory.
- Portable JSON exports contain uploaded images as Base64; importing restores them as real files.
- Original imported JSON is saved on disk; invalid imports are rejected.
- Deleting all sample quizzes does not reseed them after a restart.
- Browser workflow: host sign-in, editor, image upload, quiz save, lobby, mobile MCQ/open answers,
  player refresh while answering, scoreboard, podium and dual simulator.
- No JavaScript page errors in the browser workflow; no horizontal overflow at 390 px mobile width.
- Thai glyphs supplied by bundled local Noto Sans Thai fonts; inspected desktop and mobile screenshots.
- JavaScript syntax and Compose YAML parse checks.

## Not verified here

- Docker image build, image startup and Docker volume lifecycle on a Docker Engine.
  This environment does not provide Docker or a Docker daemon. The server was tested
  directly using the same Python application and pinned direct dependencies.
- Hardware capacity / 200 concurrent players. `MAX_PLAYERS=200` is a configurable limit,
  not a measured throughput guarantee.
- NGINX/TLS deployment and devices outside the test browser.
- Audio output was not evaluated by listening; oscillator code is exercised in the browser.

Runtime sessions are in memory. Quizzes, uploads and imported JSON are durable files.
Restarting the process ends active games.
