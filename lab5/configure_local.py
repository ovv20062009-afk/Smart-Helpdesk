"""Создаёт локальные токены. Секреты не включаются в отчёт и Git."""
import argparse
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def local_environment():
    env = os.environ.copy()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if key in ("APP_DEMO_TOKEN", "APP_READONLY_TOKEN"):
                    env.setdefault(key, value)
    if not env.get("APP_DEMO_TOKEN") or not env.get("APP_READONLY_TOKEN"):
        raise SystemExit("Сначала выполните: python configure_local.py init")
    if env["APP_DEMO_TOKEN"] == env["APP_READONLY_TOKEN"]:
        raise SystemExit("Токены должны отличаться")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "show-token", "serve"])
    args = parser.parse_args()
    if args.action == "init":
        if ENV_FILE.exists():
            local_environment()
            print("Локальный .env уже существует, токены сохранены.")
            return
        with ENV_FILE.open("x", encoding="utf-8") as file:
            file.write("APP_DEMO_TOKEN=" + secrets.token_urlsafe(32) + "\n")
            file.write("APP_READONLY_TOKEN=" + secrets.token_urlsafe(32) + "\n")
        try:
            ENV_FILE.chmod(0o600)
        except OSError:
            pass
        print("Создан локальный .env с двумя разными токенами. Не публикуйте этот файл.")
    elif args.action == "show-token":
        # Вывод выполняется только по явной команде для ручной авторизации Swagger.
        print(local_environment()["APP_DEMO_TOKEN"])
    else:
        import subprocess
        import sys
        raise SystemExit(subprocess.call([sys.executable, "-m", "uvicorn", "src.api:app", "--host", "127.0.0.1",
            "--port", "8000", "--workers", "1", "--no-access-log", "--log-config", "src/logging.json"],
            cwd=ROOT, env=local_environment()))


if __name__ == "__main__":
    main()
