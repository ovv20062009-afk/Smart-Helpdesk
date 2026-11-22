"""Явная передача настроек локальному процессу Streamlit."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def settings(fallback=False):
    env = os.environ.copy()
    token = env.get("API_TOKEN", "")
    if not token:
        token = env.get("APP_DEMO_TOKEN", "")
    if not token:
        path = ROOT / "lab5/.env"
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if line.startswith("APP_DEMO_TOKEN="):
                    token = line.split("=", 1)[1]
                    break
    if not token:
        raise SystemExit("Нет локального токена. Сначала выполните configure_local.py init из lab5.")
    env["API_TOKEN"] = token
    env["API_URL"] = "http://127.0.0.1:8001" if fallback else env.get("API_URL", "http://127.0.0.1:8000")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fallback", action="store_true", help="Использовать резервный контейнер на порту 8001")
    args = parser.parse_args()
    raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run", "frontend/app.py",
        "--server.address", "127.0.0.1", "--server.port", "8501", "--server.headless", "true"],
        cwd=ROOT, env=settings(args.fallback)))


if __name__ == "__main__":
    main()
