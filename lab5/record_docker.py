"""Проверяет настоящий контейнер и сохраняет результаты для отчёта."""
import json
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
IMAGE = "smart-helpdesk:v1.0.0"
CONTAINER = "smart-helpdesk-lab5"


def inspect(kind, name):
    process = subprocess.run(["docker", kind, "inspect", name], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", check=True)
    return json.loads(process.stdout)[0]


def main():
    image = inspect("image", IMAGE)
    container = inspect("container", CONTAINER)
    if not container["State"]["Running"]:
        raise SystemExit("Контейнер не запущен. Посмотрите docker logs smart-helpdesk-lab5")
    if container["Image"] != image["Id"]:
        raise SystemExit("Контейнер запущен из другого образа")
    ports = container["NetworkSettings"]["Ports"].get("8000/tcp") or []
    if not any(item["HostPort"] == "8000" and item["HostIp"] in ("127.0.0.1", "0.0.0.0") for item in ports):
        raise SystemExit("Порт контейнера 8000 не опубликован на порту 8000 хоста")
    env = os.environ.copy()
    env["HELPDESK_URL"] = "http://127.0.0.1:8000"
    smoke = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_container.py"],
                           cwd=ROOT, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    (ROOT / "docs/container_tests.txt").write_text(smoke.stdout + smoke.stderr, encoding="utf-8")
    print(smoke.stdout)
    if smoke.returncode:
        raise SystemExit(smoke.returncode)
    # Этот список соответствует разрешениям в .dockerignore. Docker показывает
    # фактический размер переданного контекста в выводе docker build.
    included = [ROOT / name for name in ("requirements.txt", "Dockerfile", ".dockerignore",
               "artifacts/preprocessor.joblib", "artifacts/manifest.json", "models/model.joblib")]
    included += list((ROOT / "src").glob("*.py"))
    context_bytes = sum(path.stat().st_size for path in included)
    if context_bytes > 200 * 1024 * 1024:
        raise SystemExit("Размер включённых файлов превышает 200 МиБ")
    result = {"image": IMAGE, "image_id": image["Id"], "image_size_bytes": image["Size"],
              "image_size_mib": round(image["Size"] / 1024 / 1024, 2),
              "container": CONTAINER, "running": True, "port": 8000,
              "included_files_bytes": context_bytes, "smoke_tests": "passed",
              "healthcheck": container["State"].get("Health", {}).get("Status", "not_available")}
    (ROOT / "docs/docker_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
