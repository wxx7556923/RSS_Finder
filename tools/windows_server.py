from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
PID_FILE = LOG_DIR / "paper-radar-windows.pid"
WEB_LOG = LOG_DIR / "web.log"
URL = "http://127.0.0.1:8090/?mode=original"


def _ensure_dirs() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "output").mkdir(exist_ok=True)


def _is_url_ready(timeout: float = 1.5) -> bool:
    try:
        with urlopen(URL, timeout=timeout) as response:
            return 200 <= response.status < 500
    except URLError:
        return False
    except TimeoutError:
        return False


def _port_is_busy(host: str = "127.0.0.1", port: int = 8090) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.8)
        return sock.connect_ex((host, port)) == 0


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _process_running(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return f'"{pid}"' in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start() -> int:
    _ensure_dirs()
    if _is_url_ready():
        print(f"Paper Radar is already running: {URL}")
        return 0

    process: subprocess.Popen[str] | None = None
    pid = _read_pid()
    if pid and _process_running(pid):
        print(f"Paper Radar process exists, waiting for web service: pid {pid}")
    else:
        print("Starting Paper Radar server...")
        log_handle = WEB_LOG.open("a", encoding="utf-8")
        log_handle.write("\n--- starting Paper Radar ---\n")
        log_handle.flush()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.web:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8090",
            ],
            cwd=ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        PID_FILE.write_text(str(process.pid), encoding="utf-8")

    for _ in range(30):
        if _is_url_ready():
            print(f"Paper Radar is running: {URL}")
            return 0
        if process is not None and process.poll() is not None:
            print(f"Paper Radar server exited early with code {process.returncode}.")
            _print_recent_logs()
            return 1
        time.sleep(1)

    print("Paper Radar did not become ready within 30 seconds.")
    print(f"Check logs with Windows-Logs.bat. Log file: {WEB_LOG}")
    _print_recent_logs()
    return 1


def stop() -> int:
    pid = _read_pid()
    if not pid:
        print("No Paper Radar pid file found.")
        return 0
    if not _process_running(pid):
        print("Paper Radar is not running.")
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        return 0
    print(f"Stopping Paper Radar pid {pid}...")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        os.kill(pid, 15)
    try:
        PID_FILE.unlink()
    except OSError:
        pass
    print("Stopped.")
    return 0


def status() -> int:
    if _is_url_ready():
        print(f"Paper Radar is running: {URL}")
        return 0
    pid = _read_pid()
    if pid and _process_running(pid):
        print(f"Process exists but web service is not ready: pid {pid}")
        return 1
    print("Paper Radar is stopped.")
    return 0


def logs(lines: int = 120) -> int:
    if not WEB_LOG.exists():
        print("No web log found yet.")
        return 0
    content = WEB_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in content[-lines:]:
        print(line)
    return 0


def _print_recent_logs(lines: int = 80) -> None:
    print()
    print(f"Recent web log: {WEB_LOG}")
    if not WEB_LOG.exists():
        print("No web log found.")
        return
    content = WEB_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    if not content:
        print("Web log is empty.")
        return
    for line in content[-lines:]:
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Paper Radar on Windows.")
    parser.add_argument("command", choices=["start", "stop", "status", "logs"])
    args = parser.parse_args()
    if args.command == "start":
        return start()
    if args.command == "stop":
        return stop()
    if args.command == "status":
        return status()
    if args.command == "logs":
        return logs()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
