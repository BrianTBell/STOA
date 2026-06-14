"""Launch and stop the local STOA API and frontend."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = Path(__file__).resolve().parent / ".runtime"
STATE_PATH = RUNTIME_DIR / "state.json"
API_LOG_PATH = RUNTIME_DIR / "api.log"
FRONTEND_LOG_PATH = RUNTIME_DIR / "frontend.log"
API_ADDRESS = ("127.0.0.1", 8000)
FRONTEND_ADDRESS = ("127.0.0.1", 5173)
FRONTEND_URL = "http://127.0.0.1:5173"
STARTUP_TIMEOUT_SECONDS = 30


def port_is_open(address: tuple[str, int]) -> bool:
    try:
        with socket.create_connection(address, timeout=0.25):
            return True
    except OSError:
        return False


def process_is_running(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        rows = list(csv.reader(io.StringIO(result.stdout)))
        return bool(rows and len(rows[0]) > 1 and rows[0][1] == str(pid))
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def pid_listening_on(address: tuple[str, int]) -> int | None:
    if sys.platform != "win32":
        return None
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        check=False,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    expected_port = str(address[1])
    for line in result.stdout.splitlines():
        columns = line.split()
        if (
            len(columns) >= 5
            and columns[0] == "TCP"
            and columns[1].rsplit(":", 1)[-1] == expected_port
            and columns[3] == "LISTENING"
        ):
            return int(columns[4])
    return None


def read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(api_pid: int, frontend_pid: int) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "api_pid": api_pid,
                "frontend_pid": frontend_pid,
                "started_at": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def tail_log(path: Path, line_count: int = 8) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return "No log output was written."
    return "\n".join(lines[-line_count:])


def start_process(
    command: list[str],
    cwd: Path,
    log_path: Path,
) -> subprocess.Popen[bytes]:
    RUNTIME_DIR.mkdir(exist_ok=True)
    log_file = log_path.open("wb")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )

    try:
        return subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
    finally:
        log_file.close()


def wait_for_process(
    name: str,
    process: subprocess.Popen[bytes],
    address: tuple[str, int],
    log_path: Path,
) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if port_is_open(address):
            return
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"{name} exited with code {return_code}.\n\n{tail_log(log_path)}"
            )
        time.sleep(0.25)
    raise RuntimeError(
        f"{name} did not open port {address[1]} within "
        f"{STARTUP_TIMEOUT_SECONDS} seconds.\n\n{tail_log(log_path)}"
    )


def stop_process_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return
    os.kill(pid, 15)


def launch(open_browser: bool = True) -> None:
    state = read_state()
    known_pids = [
        int(state[key])
        for key in ("api_pid", "frontend_pid")
        if state.get(key) is not None
    ]
    if any(process_is_running(pid) for pid in known_pids):
        raise RuntimeError("STOA is already running. Use `reboot` to restart it.")
    if port_is_open(API_ADDRESS) or port_is_open(FRONTEND_ADDRESS):
        raise RuntimeError(
            "Port 8000 or 5173 is already in use. Stop that process before "
            "launching STOA."
        )

    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if npm is None:
        raise RuntimeError("npm was not found. Install Node.js before launching STOA.")

    print("Launching STOA API...")
    api_process = start_process(
        [sys.executable, "-m", "backend.api"],
        ROOT,
        API_LOG_PATH,
    )
    frontend_process: subprocess.Popen[bytes] | None = None
    try:
        wait_for_process("The API", api_process, API_ADDRESS, API_LOG_PATH)
        print("Launching STOA frontend...")
        frontend_process = start_process(
            [npm, "run", "dev", "--", "--host", FRONTEND_ADDRESS[0]],
            ROOT / "frontend",
            FRONTEND_LOG_PATH,
        )
        wait_for_process(
            "The frontend",
            frontend_process,
            FRONTEND_ADDRESS,
            FRONTEND_LOG_PATH,
        )
    except Exception:
        stop_process_tree(api_process.pid)
        if frontend_process is not None:
            stop_process_tree(frontend_process.pid)
        STATE_PATH.unlink(missing_ok=True)
        raise

    api_pid = pid_listening_on(API_ADDRESS) or api_process.pid
    frontend_pid = pid_listening_on(FRONTEND_ADDRESS) or frontend_process.pid
    write_state(api_pid, frontend_pid)
    print(f"STOA is running at {FRONTEND_URL}")
    print(f"Logs: {RUNTIME_DIR}")
    if open_browser:
        webbrowser.open(FRONTEND_URL)


def shutdown() -> None:
    state = read_state()
    recorded_pids = [
        int(state[key])
        for key in ("frontend_pid", "api_pid")
        if state.get(key) is not None
    ]
    listening_pids = [
        pid
        for pid in (
            pid_listening_on(FRONTEND_ADDRESS),
            pid_listening_on(API_ADDRESS),
        )
        if pid is not None
    ]
    pids = list(dict.fromkeys(recorded_pids + listening_pids))
    if not pids:
        print("STOA is not running.")
        return

    for pid in pids:
        stop_process_tree(pid)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not port_is_open(API_ADDRESS) and not port_is_open(FRONTEND_ADDRESS):
            break
        time.sleep(0.1)
    STATE_PATH.unlink(missing_ok=True)
    if port_is_open(API_ADDRESS) or port_is_open(FRONTEND_ADDRESS):
        raise RuntimeError(
            "STOA could not be shut down. Check whether another process owns "
            "port 8000 or 5173."
        )
    print("STOA has shut down.")


def reboot(open_browser: bool = True) -> None:
    shutdown()
    launch(open_browser=open_browser)


def status() -> None:
    api_running = port_is_open(API_ADDRESS)
    frontend_running = port_is_open(FRONTEND_ADDRESS)
    print(f"API: {'running' if api_running else 'stopped'}")
    print(f"Frontend: {'running' if frontend_running else 'stopped'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("launch", "reboot", "shutdown", "status"),
        help="Action to perform.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the frontend in the default browser.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.action == "launch":
            launch(open_browser=not args.no_browser)
        elif args.action == "reboot":
            reboot(open_browser=not args.no_browser)
        elif args.action == "shutdown":
            shutdown()
        else:
            status()
    except RuntimeError as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
