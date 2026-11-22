"""Проверка JSONL и связанного запроса в логе Docker или Uvicorn."""
import json
from pathlib import Path
import sys
from uuid import UUID


def main():
    path = Path(sys.argv[1])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not records:
        raise SystemExit("Лог пуст")
    complete = [item for item in records if item.get("message") == "request_complete"]
    if not complete:
        raise SystemExit("Нет завершённых HTTP-запросов")
    for item in complete:
        assert UUID(item["trace_id"]).version == 4
        assert item["latency_ms"] >= 0
    traces = {item["trace_id"] for item in complete}
    if len(sys.argv) > 2 and sys.argv[2] not in traces:
        raise SystemExit("Указанный trace_id не найден")
    print(json.dumps({"valid_json_lines": len(records), "requests": len(complete)}, indent=2))


if __name__ == "__main__":
    main()
