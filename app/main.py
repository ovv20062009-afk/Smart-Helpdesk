import json
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST, generate_latest

from app.api.schemas import HealthResponse, PredictionRequest, PredictionResponse
from app.ml.inference import ModelLoader
from app.repositories.audit import check_database, save_prediction
from app.services.prediction import build_prediction

app = FastAPI(title="Smart Helpdesk API", version="1.1.0")
model = ModelLoader()
started_at = monotonic()
logger = logging.getLogger("lab2")
logging.basicConfig(level=logging.INFO, format="%(message)s")
requests_total = Counter("http_requests_total", "HTTP requests", ["endpoint", "status"])
request_seconds = Histogram("http_request_duration_seconds", "HTTP duration", ["endpoint"])
inference_seconds = Histogram("model_inference_duration_seconds", "Inference duration")


def database_path():
    return os.getenv("AUDIT_DB", "runtime/audit.sqlite3")


@app.middleware("http")
async def trace_request(request: Request, call_next):
    start = monotonic()
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    endpoint = request.url.path if request.url.path in {"/api/v1/predict", "/health", "/metrics"} else "other"
    elapsed = monotonic() - start
    requests_total.labels(endpoint, str(response.status_code)).inc()
    request_seconds.labels(endpoint).observe(elapsed)
    response.headers["X-Request-ID"] = request.state.request_id
    logger.info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request.state.request_id, "endpoint": endpoint,
        "status": response.status_code, "latency_ms": round(elapsed * 1000, 2),
        "prediction": getattr(request.state, "prediction", None), "model_version": model.version}))
    return response


def check_api_key(value):
    expected = os.getenv("API_KEY")
    if not expected:
        raise HTTPException(503, "API_KEY is not configured")
    if value is None or not secrets.compare_digest(value.encode(), expected.encode()):
        raise HTTPException(401, "Invalid X-API-Key")


@app.post("/api/v1/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest, request: Request,
            x_api_key: str | None = Header(default=None)) -> PredictionResponse:
    check_api_key(x_api_key)
    if not model.loaded:
        raise HTTPException(503, "Model is not ready")
    with inference_seconds.time():
        result = build_prediction(payload, model)
    result.request_id = request.state.request_id
    try:
        save_prediction(database_path(), result.model_dump(), {"text_length": len(payload.text)})
    except (OSError, sqlite3.Error):
        raise HTTPException(503, "Audit storage is unavailable")
    request.state.prediction = result.category
    return result


@app.get("/health", response_model=HealthResponse)
def health():
    ready = model.loaded and check_database(database_path()) and bool(os.getenv("API_KEY"))
    result = HealthResponse(status="healthy" if ready else "unhealthy", model_loaded=model.loaded,
                            model_version=model.version, uptime_seconds=round(monotonic() - started_at, 2))
    return JSONResponse(result.model_dump(), status_code=200 if ready else 503)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
