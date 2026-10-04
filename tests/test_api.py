import os
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.main import app, model
from app.api.schemas import PredictionRequest
from app.ml.preprocessing import tokenize
from app.services.prediction import build_prediction

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("AUDIT_DB", str(tmp_path / "audit.sqlite3"))
    with TestClient(app) as c:
        yield c

def send(client, text, **extra):
    return client.post("/api/v1/predict", headers={"X-API-Key": "test-key"},
                       json={"ticket_id": "T-1", "text": text, **extra})

@pytest.mark.parametrize("text,category,destination", [
    ("Не могу войти, забыла пароль", "TECHNICAL", "IT_SUPPORT"),
    ("Оплата прошла, нужна квитанция", "PAYMENT", "FINANCE"),
    ("Где расписание, когда экзамен?", "STUDY", "STUDENT_OFFICE"),
])
def test_routes(client,text,category,destination):
    response=send(client,text)
    assert response.status_code==200
    data=response.json()
    assert data["category"]==category and data["destination"]==destination
    assert data["manual_review_required"] is False
    assert data["request_id"]==response.headers["X-Request-ID"]

@pytest.mark.parametrize("text",["Спасибо за помощь", "Забыла пароль", "пароль оплата"])
def test_fallback(client,text):
    data=send(client,text).json()
    assert data["confidence"]<0.8
    assert data["destination"]=="OPERATOR" and data["manual_review_required"]

@pytest.mark.parametrize("confidence,manual",[(0.79,True),(0.8,False)])
def test_threshold(confidence,manual):
    class FixedModel:
        version="test"
        def predict(self,text): return "TECHNICAL",confidence
    result=build_prediction(PredictionRequest(ticket_id="T",text="example"),FixedModel())
    assert result.manual_review_required is manual

@pytest.mark.parametrize("text",["", "   ", "a"*5001])
def test_validation(client,text):
    assert send(client,text).status_code==422

def test_auth(client):
    assert client.post("/api/v1/predict",json={"ticket_id":"T", "text":"пароль"}).status_code==401

def test_audit_no_raw_text(client):
    text="Не могу войти, пароль. user@example.com"
    result=send(client,text).json()
    with sqlite3.connect(os.environ["AUDIT_DB"]) as db:
        row=db.execute("SELECT request_id,result,features FROM predictions").fetchone()
    assert row[0]==result["request_id"]
    assert "user@example.com" not in str(row) and text not in str(row)

def test_health(client,monkeypatch):
    assert client.get("/health").status_code==200
    monkeypatch.setattr(model,"loaded",False)
    assert client.get("/health").status_code==503
    assert send(client,"пароль").status_code==503

def test_metrics(client):
    response=client.get("/metrics")
    assert response.status_code==200 and "# EOF" in response.text

def test_preprocessing():
    tokens=tokenize("ПАРОЛЬ! user@example.com +7 (900) 123-45-67")
    assert "пароль" in tokens and "user" not in tokens
