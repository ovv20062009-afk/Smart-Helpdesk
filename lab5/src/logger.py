"""JSON Lines в stdout без исходных текстов, заголовков и traceback."""
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys

trace_context: ContextVar[str | None] = ContextVar("trace_id", default=None)
ALLOWED_FIELDS = {"trace_id", "ticket_id", "source", "category", "destination",
                  "manual_review_required", "latency_ms", "status_code", "method",
                  "path", "model_version", "model_available", "error_type"}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        item = {"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname, "logger": record.name,
                "message": record.getMessage()}
        trace_id = trace_context.get()
        if trace_id:
            item["trace_id"] = trace_id
        extra = getattr(record, "extra_data", {})
        if isinstance(extra, dict):
            item.update({key: value for key, value in extra.items() if key in ALLOWED_FIELDS})
        if record.exc_info and record.exc_info[0]:
            item["error_type"] = record.exc_info[0].__name__
        return json.dumps(item, ensure_ascii=False, allow_nan=False)


def get_json_logger(name: str = "smart_helpdesk") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    return logger
