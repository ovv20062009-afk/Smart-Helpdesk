"""История одного сеанса и экспорт только разрешённых полей."""
import pandas as pd

MAX_HISTORY = 100
COLUMNS = ["requested_at", "ticket_id", "text", "channel", "status", "confidence",
           "category", "destination", "manual_review_required", "threshold_used", "source", "degraded",
           "model_version", "preprocessor_version", "trace_id", "server_timestamp", "server_ms", "client_ms", "error_code"]


def make_row(payload, requested_at, client_ms, result=None, error=None):
    row = {key: None for key in COLUMNS}
    row.update({key: payload.get(key) for key in ("ticket_id", "text", "channel")})
    row.update(requested_at=requested_at, client_ms=round(client_ms, 3))
    if error is not None:
        row.update(status="error", error_code=error.code, trace_id=error.trace_id)
    else:
        p, m = result.prediction, result.metadata
        row.update(status="degraded" if m.degraded else "manual" if p.manual_review_required else "success",
            confidence=p.confidence, category=p.category, destination=p.destination,
            manual_review_required=p.manual_review_required, threshold_used=p.threshold_used,
            source=m.source, degraded=m.degraded, model_version=m.model_version,
            preprocessor_version=m.preprocessor_version, trace_id=str(result.trace_id),
            server_timestamp=m.timestamp_utc.isoformat(), server_ms=m.latency_ms)
    return row


def append_history(history, row):
    return (history + [row])[-MAX_HISTORY:]


def spreadsheet_text(value):
    # Кавычки CSV сами по себе не мешают таблице выполнить формулу.
    if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))):
        return "'" + value
    return value


def export_csv(history):
    rows = [{key: spreadsheet_text(row.get(key)) for key in COLUMNS} for row in history]
    return pd.DataFrame(rows, columns=COLUMNS).to_csv(index=False, na_rep="").encode("utf-8-sig")
