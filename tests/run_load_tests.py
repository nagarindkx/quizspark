"""Reproduce local 200-player tests using separate server and load processes.

python tests/run_load_tests.py [--baseline /path/to/v3.0/app/server.py]
Only starts temporary, loopback servers; use tools/stress_test.py for deployment.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def run(app, output, name, rounds, ramp, spread=0, concurrency=10):
    with socket.socket() as allocation:
        allocation.bind(("127.0.0.1", 0))
        port = allocation.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix="quizspark-load-") as directory:
        with (output / (name + ".server.log")).open("w") as log:
            server = subprocess.Popen([sys.executable, str(app)],
                                      env={**os.environ, "DATA_DIR": directory, "PORT": str(port),
                                           "ADMIN_PASSWORD": password, "MAX_PLAYERS": "200"},
                                      stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(url + "/health", timeout=1) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        if server.poll() is not None:
                            raise RuntimeError("Server exited; inspect " + name + ".server.log")
                        time.sleep(.05)
                else:
                    raise RuntimeError("Server startup timed out")
                report = output / (name + ".json")
                command = [sys.executable, str(ROOT / "tools/stress_test.py"), "--url", url,
                           "--players", "200", "--rounds", str(rounds), "--question-seconds", "20",
                           "--ramp-seconds", str(ramp), "--answer-spread", str(spread),
                           "--join-concurrency", str(concurrency), "--output", str(report)]
                result = subprocess.run(command, env={**os.environ, "QUIZSPARK_ADMIN_PASSWORD": password}, timeout=300)
                data = json.loads(report.read_text())
                data["verification"] = {"server": health, "load_exit_code": result.returncode,
                                        "server_process_separate": True, "transport": "loopback HTTP/WebSocket",
                                        "created_utc": datetime.now(timezone.utc).isoformat(),
                                        "platform": platform.platform(), "logical_cpus_visible": os.cpu_count(),
                                        "python": platform.python_version()}
                for field, location in (("cpu_quota", "/sys/fs/cgroup/cpu.max"),
                                        ("memory_limit_bytes", "/sys/fs/cgroup/memory.max")):
                    try:
                        data["verification"][field] = Path(location).read_text().strip()
                    except OSError:
                        pass
                report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                return data["status"] == "PASS" and all(not c["cleanup_errors"] for c in data["cases"])
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, help="Optional original v3.0 app/server.py")
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/load")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.baseline:
        run(args.baseline.resolve(), args.output, "baseline-burst-200", 2, 2)
    app = ROOT / "app/server.py"
    passed = []
    # A new temporary process per scenario resets the per-IP connection quota.
    for name, rounds, ramp, spread, concurrency in [
        ("burst-200", 5, 2, 0, 10),
        ("spread-200", 3, 2, 10, 10),
        ("join-burst-200", 5, 0, 0, 200),
    ]:
        passed.append(run(app, args.output, name, rounds, ramp, spread, concurrency))
    return 0 if all(passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
