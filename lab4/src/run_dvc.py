"""Запускает DVC и его стадии тем же Python, которым вызван этот модуль."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    raise SystemExit(subprocess.call([sys.executable, "-m", "dvc", *sys.argv[1:]], env=env))


if __name__ == "__main__":
    main()
