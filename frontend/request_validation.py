"""Клиентская проверка полей контракта ЛР 7. Сервер проверяет их повторно."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=5000)
    channel: Literal["web", "email", "chat"] = "web"

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value):
        # Сервер также распознаёт телефон как контакт, даже если в тексте нет букв.
        has_letters = re.search(r"[a-zа-яё]", value.lower())
        has_phone = re.search(r"\+?\d[\d ()-]{8,}\d", value)
        if not has_letters and not has_phone:
            raise ValueError("Введите текст обращения")
        return value
