#!/usr/bin/env python3
"""
Dev runner for Notes Copilot (Windows-friendly)
- Starts FastAPI backend with uvicorn
- Starts Vite frontend (npm run dev) in ./web
- Wires env so the two talk to each other
- Opens the browser to the frontend
- Gracefully shuts both on Ctrl+C
"""

from __future__ import annotations
import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional

# ---------------- helpers ----------------

def which(cmd: str) -> Optional[str]:
    from shutil import which as _which
    return _which(cmd)

def wait_for_http(url: str, timeout: float = 30.0) -> bool:
    """Ping a URL until it returns any 2xx–4xx (i.e., server is up)."""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if 200 <= r.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False

def popen_stream(cmd: str, *, cwd: str | None = None, env: dict | None = None) -> subprocess.Popen:
    """
    Start a subprocess and stream stdout+stderr line-by-line.
    Use shell=True so 'npm run dev' works on Windows without extra hassle.
    """
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        shell=True,  # important for Windows npm scripts
        preexec_fn=None if os.name == "nt" else os.setsid,
    )

def stream_output(prefix: str, proc: subprocess.Popen) -> None:
    try:
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                sys.stdout.write(f"[{prefix}] {line}")
    except Exception:
        pass

def kill_proc_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass

def detect_backend_import(root: Path) -> str:
    """
    Try to find a module path like 'main:app' or 'api.main:app'.
    Falls back to the user-specified default.
    """
    candidates = [
        ("main.py", "main:app"),
        ("app.py", "app:app"),
        ("api/main.py", "api.main:app"),
        ("server/main.py", "server.main:app"),
        ("src/main.py", "src.main:app"),
    ]
    for rel, mod in candidates:
        if (root / rel).exists():
            return mod
    # last resort: keep user flag default
    return ""

# ---------------- main ----------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Dev runner for backend + frontend")
    parser.add_argument("--backend", default="auto", help="Uvicorn app import path (e.g., api.main:app or 'auto')")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-dir", default="web")
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--frontend-cmd", default=None, help="Override frontend start command")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    frontend_dir = (root / args.frontend_dir).resolve()

    # sanity checks
    if which("uvicorn") is None:
        print("ERROR: uvicorn not found. Install it in your venv:  pip install uvicorn fastapi")
        sys.exit(1)
    if which("npm") is None:
        print("ERROR: npm not found on PATH. Install Node.js from https://nodejs.org and restart your terminal.")
        sys.exit(1)
    if not frontend_dir.exists():
        print(f"ERROR: Frontend directory not found: {frontend_dir}")
        sys.exit(1)

    # load .env (optional)
    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        print("✓ Loaded .env")
    except Exception as e:
        print(f"⚠ Could not load .env: {e}")

    # Decide backend import path
    backend_import = args.backend if args.backend != "auto" else detect_backend_import(root)
    if not backend_import:
        backend_import = "main:app"  # safe default if auto failed

    # shared env
    env = os.environ.copy()
    env["FRONTEND_ORIGIN"] = f"http://localhost:{args.frontend_port}"
    # IMPORTANT: include /api
    env["VITE_API_URL"] = f"http://{args.backend_host}:{args.backend_port}/api"
    env.setdefault("DATA_DIR", str((root / "data").resolve()))
    # keep Vite from auto-opening multiple windows
    env.setdefault("BROWSER", "none")

    print("==> Environment")
    print("FRONTEND_ORIGIN =", env["FRONTEND_ORIGIN"])
    print("VITE_API_URL    =", env["VITE_API_URL"])
    print("DATA_DIR        =", env["DATA_DIR"])
    print()

    # backend command
    backend_cmd = (
        f"{sys.executable} -m uvicorn {backend_import} "
        f"--host {args.backend_host} --port {args.backend_port} --reload"
    )
    print("==> Starting backend:", backend_cmd)
    backend_proc = popen_stream(backend_cmd, env=env)

    # frontend command (port from flag)
    frontend_cmd = args.frontend_cmd or f"npm run dev -- --port {args.frontend_port}"
    print(f"==> Starting frontend in {frontend_dir} with: {frontend_cmd}")
    frontend_proc = popen_stream(frontend_cmd, cwd=str(frontend_dir), env=env)

    # stream logs
    import threading
    t1 = threading.Thread(target=stream_output, args=("backend", backend_proc), daemon=True)
    t2 = threading.Thread(target=stream_output, args=("frontend", frontend_proc), daemon=True)
    t1.start(); t2.start()

    # wait for readiness & open browser
    backend_health = f"http://{args.backend_host}:{args.backend_port}/api/health"  # <-- /api/health
    frontend_url = f"http://localhost:{args.frontend_port}/"

    print("\n==> Waiting for backend health ...")
    if wait_for_http(backend_health, timeout=60):
        print("Backend is up:", backend_health)
    else:
        print("WARNING: backend health check did not pass in time.")

    print("==> Waiting for frontend ...")
    if wait_for_http(frontend_url, timeout=60):
        print("Frontend is up:", frontend_url)
        if not args.no_open:
            try:
                webbrowser.open(frontend_url)
            except Exception:
                pass
    else:
        print("WARNING: frontend did not respond in time.")

    # keep both alive until one exits or Ctrl+C
    try:
        while True:
            time.sleep(0.5)
            if backend_proc.poll() is not None:
                print("\n** Backend process exited. Stopping dev runner.")
                break
            if frontend_proc.poll() is not None:
                print("\n** Frontend process exited. Stopping dev runner.")
                break
    except KeyboardInterrupt:
        print("\n==> Ctrl+C received, shutting down...")

    kill_proc_tree(frontend_proc)
    kill_proc_tree(backend_proc)
    print("==> All processes terminated.")

if __name__ == "__main__":
    main()
