import json
import sqlite3
from pathlib import Path


def save_prediction(path: str, result: dict, features: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=2) as db:
        db.execute("CREATE TABLE IF NOT EXISTS predictions "
                   "(request_id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
                   "result TEXT, features TEXT)")
        db.execute("INSERT INTO predictions (request_id, result, features) VALUES (?, ?, ?)",
                   (result["request_id"], json.dumps(result), json.dumps(features)))


def check_database(path: str) -> bool:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=2) as db:
            db.execute("SELECT 1")
        return True
    except (OSError, sqlite3.Error):
        return False
