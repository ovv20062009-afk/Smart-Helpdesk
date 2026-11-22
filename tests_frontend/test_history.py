import csv
from datetime import datetime, timezone
import io

import pytest

from frontend.api_client import ApiClientError
from frontend.history import append_history, export_csv, make_row
from frontend.response_validation import ApiResponse


def test_success_error_csv_and_no_secrets(body, payload):
    requested = datetime.now(timezone.utc).isoformat()
    payload["API_TOKEN"] = "DO_NOT_EXPORT"
    good = make_row(payload, requested, 12.5, result=ApiResponse.model_validate(body))
    bad = make_row(payload, requested, 20, error=ApiClientError("timeout", "Не получено"))
    assert bad["confidence"] is None and bad["source"] is None
    data = export_csv([good, bad])
    assert data.startswith(b"\xef\xbb\xbf") and b"DO_NOT_EXPORT" not in data
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[0]["confidence"] == "0.72"
    assert rows[1]["confidence"] == "" and rows[1]["error_code"] == "timeout"
    assert rows[1]["trace_id"] == ""
    assert "API_TOKEN" not in rows[0] and "Authorization" not in rows[0]


@pytest.mark.parametrize("text", ["=HYPERLINK(1)", "+cmd", "-10+2", "@SUM(A1)", "  =1+2", "\tformula", "\rformula", "\nformula"])
def test_spreadsheet_formula_protection(text):
    rows = list(csv.DictReader(io.StringIO(export_csv([{"text": text}]).decode("utf-8-sig"))))
    assert rows[0]["text"] == "'" + text


def test_history_has_limit_and_keeps_newest():
    history = []
    for i in range(105):
        history = append_history(history, {"ticket_id": str(i)})
    assert len(history) == 100
    assert history[0]["ticket_id"] == "5" and history[-1]["ticket_id"] == "104"
