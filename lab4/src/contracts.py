"""Контракт исходных обращений. Пустые тексты удаляются на этапе очистки."""
import pandera.pandas as pa

CATEGORIES = ["TECHNICAL", "PAYMENT", "STUDY"]
CHANNELS = ["web", "email", "chat"]

RawTicketsSchema = pa.DataFrameSchema({
    "ticket_id": pa.Column(str, pa.Check.str_matches(r"^T-\d{4}$")),
    "created_at": pa.Column(pa.DateTime),
    "text": pa.Column(str, pa.Check.str_length(max_value=5000), nullable=True),
    "channel": pa.Column(str, pa.Check.isin(CHANNELS), nullable=True),
    "category": pa.Column(str, pa.Check.isin(CATEGORIES)),
}, strict=True, coerce=True, unique=["ticket_id"])
