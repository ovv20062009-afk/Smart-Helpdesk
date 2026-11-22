"""Учебные Bearer-токены: прогноз или доступ без права прогноза."""
from dataclasses import dataclass
import os
import secrets

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False, description="Локальный токен из APP_DEMO_TOKEN или APP_READONLY_TOKEN")


@dataclass(frozen=True)
class Client:
    client_id: str
    can_predict: bool


@dataclass(frozen=True)
class TokenConfig:
    predict_token: str
    readonly_token: str

    @classmethod
    def from_environment(cls):
        return cls(os.getenv("APP_DEMO_TOKEN", ""), os.getenv("APP_READONLY_TOKEN", ""))

    @property
    def configured(self):
        return bool(self.predict_token) and self.predict_token != self.readonly_token


def verify_token(request: Request,
                 credentials: HTTPAuthorizationCredentials | None = Security(bearer)) -> Client:
    config = request.app.state.tokens
    if not config.configured:
        raise HTTPException(503, "Учетные данные сервиса не настроены")
    token = credentials.credentials if credentials else ""
    supplied = token.encode("utf-8")
    if token and secrets.compare_digest(supplied, config.predict_token.encode("utf-8")):
        return Client("helpdesk_demo", True)
    if token and config.readonly_token and secrets.compare_digest(supplied, config.readonly_token.encode("utf-8")):
        return Client("helpdesk_readonly", False)
    raise HTTPException(401, "Недействительные учетные данные", headers={"WWW-Authenticate": "Bearer"})


def require_predict(client: Client = Security(verify_token)) -> Client:
    if not client.can_predict:
        raise HTTPException(403, "Действие запрещено")
    return client
