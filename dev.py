# dev.py
from __future__ import annotations
import os, sys, time, signal, subprocess, webbrowser
from pathlib import Path

def main():
    repo = Path(__file__).resolve().parent
    os.chdir(repo)  # important so relative paths work

    # Load .env into current process, then inherit to children
    try:
        from dotenv import load_dotenv
        load_dotenv(repo / ".env")
    except Exception:
        pass  # optional; fine if not installed

    # Defaults (override via .env or shell)
    API_PORT = os.getenv("API_PORT", "8000")
    UI_PORT = os.getenv("UI_PORT", "8501")
    HEADLESS = os.getenv("UI_HEADLESS", "true")  # "true"/"false"
    OPEN_BROWSER = os.getenv("OPEN_BROWSER", "true")  # "true"/"false"

    # Ensure Python can import "api" and "core" when tools introspect paths
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    venv_bin = repo / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    if venv_bin.exists():
        env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
        python_exec = str(venv_bin / ("python.exe" if os.name == "nt" else "python"))
    else:
        python_exec = sys.executable

    api_cmd = [python_exec, "-m", "uvicorn", "api.main:app", "--reload", "--port", API_PORT]
    ui_cmd = [python_exec, "-m", "streamlit", "run", "ui/app.py", "--server.port", UI_PORT, "--server.headless", HEADLESS]

    procs: list[subprocess.Popen] = []

    def spawn(name: str, cmd: list[str]):
        print(f"▶ starting {name}: {' '.join(cmd)}")
        p = subprocess.Popen(cmd, env=env)
        procs.append(p)
        return p

    def shutdown(*_):
        print("\n⏹ shutting down...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        # give them a moment; then be brutal
        time.sleep(0.8)
        for p in procs:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass
        sys.exit(0)

    # Clean exit on Ctrl+C / SIGTERM
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Launch API then UI
    api = spawn("API (Uvicorn)", api_cmd)
    # small delay so Streamlit can show API link
    time.sleep(0.6)
    ui = spawn("Frontend (Streamlit)", ui_cmd)

    # Open browser to Streamlit (optional)
    if OPEN_BROWSER.lower() == "true":
        url = f"http://localhost:{UI_PORT}"
        # tiny wait so streamlit binds the port
        time.sleep(1.2)
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            pass

    # Wait until either process exits; then shut down the other
    while True:
        rc_api = api.poll()
        rc_ui = ui.poll()
        if rc_api is not None or rc_ui is not None:
            break
        time.sleep(0.5)
    shutdown()

if __name__ == "__main__":
    main()
