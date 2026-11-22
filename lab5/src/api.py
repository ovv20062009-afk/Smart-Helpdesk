"""Устойчивый API Smart Helpdesk с JSONL и сквозным trace_id."""
from contextlib import asynccontextmanager
from pathlib import Path
import os
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.artifacts import load_bundle, MODEL_VERSION, PREPROCESSOR_VERSION
from src.logger import get_json_logger, trace_context
from src.prediction import fallback_decision, model_decision
from src.schemas import PredictionRequest, PredictionResult

logger = get_json_logger()
SAFE_PATHS = {"/health", "/predict", "/docs", "/openapi.json", "/redoc"}


def create_app(root: Path | None = None) -> FastAPI:
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.model = None
        app.state.preprocessor = None
        app.state.last_model_error = False
        app.state.manifest = {"review_threshold": 0.8}
        try:
            if os.environ.get("HELPDESK_DISABLE_MODEL") == "1":
                raise RuntimeError("Модель отключена для проверки Fallback")
            preprocessor, model, manifest = load_bundle(root)
            app.state.preprocessor = preprocessor
            app.state.model = model
            app.state.manifest = manifest
            logger.info("artifacts_loaded", extra={"extra_data": {"model_version": MODEL_VERSION}})
        except Exception as error:
            app.state.last_model_error = True
            logger.warning("artifacts_unavailable", extra={"extra_data": {
                "error_type": type(error).__name__, "model_version": MODEL_VERSION}})
        yield
        app.state.model = None
        app.state.preprocessor = None

    app = FastAPI(title="Smart Helpdesk", version=MODEL_VERSION, lifespan=lifespan,
                  description="Маршрутизация обращений с резервным правилом и сквозными JSON-логами")

    @app.middleware("http")
    async def trace_request(request: Request, call_next):
        trace_id = str(uuid4())
        token = trace_context.set(trace_id)
        request.state.trace_id = trace_id
        request.state.started = time.perf_counter()
        request.state.log_fields = {}
        try:
            try:
                response = await call_next(request)
            except Exception as error:
                request.state.log_fields["error_type"] = type(error).__name__
                response = JSONResponse(status_code=500, content={"detail": "Ошибка сервиса", "trace_id": trace_id})
            response.headers["X-Trace-ID"] = trace_id
            duration = round((time.perf_counter() - request.state.started) * 1000, 3)
            fields = {"trace_id": trace_id, "method": request.method,
                      "path": request.url.path if request.url.path in SAFE_PATHS else "other",
                      "status_code": response.status_code, "latency_ms": duration,
                      "model_version": MODEL_VERSION}
            fields.update(request.state.log_fields)
            logger.info("request_complete", extra={"extra_data": fields})
            return response
        finally:
            trace_context.reset(token)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Стандартная ошибка Pydantic может повторить введённое значение.
        # Оставляем тип, расположение и сообщение, без input и ctx.
        details = [{"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
                   for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details, "trace_id": request.state.trace_id})

    @app.get("/health", summary="Готовность сервиса и состояние модели")
    def health(request: Request):
        loaded = app.state.model is not None and app.state.preprocessor is not None
        status = "ok" if loaded and not app.state.last_model_error else "degraded"
        return {"status": status, "model_version": MODEL_VERSION, "trace_id": request.state.trace_id,
                "model_loaded": app.state.model is not None,
                "preprocessor_loaded": app.state.preprocessor is not None,
                "fallback_available": True}

    @app.post("/predict", response_model=PredictionResult, summary="Предложить категорию и отдел")
    def predict(payload: PredictionRequest, request: Request):
        source = "model"
        try:
            if app.state.model is None or app.state.preprocessor is None:
                raise RuntimeError("Артефакты недоступны")
            decision = model_decision(payload.text, payload.channel, app.state.preprocessor,
                                      app.state.model, app.state.manifest["review_threshold"])
            app.state.last_model_error = False
        except Exception as error:
            app.state.last_model_error = True
            source = "fallback_rule"
            decision = fallback_decision(payload.text)
            logger.warning("fallback_activated", extra={"extra_data": {
                "trace_id": request.state.trace_id, "ticket_id": payload.ticket_id,
                "source": source, "error_type": type(error).__name__, "model_version": MODEL_VERSION}})
        latency = round((time.perf_counter() - request.state.started) * 1000, 3)
        request.state.log_fields = {"ticket_id": payload.ticket_id, "source": source,
            "category": decision.category, "destination": decision.destination,
            "manual_review_required": decision.manual_review_required, "latency_ms": latency}
        return PredictionResult(trace_id=request.state.trace_id, ticket_id=payload.ticket_id,
            category=decision.category, confidence=decision.confidence, destination=decision.destination,
            manual_review_required=decision.manual_review_required, model_version=MODEL_VERSION,
            preprocessor_version=PREPROCESSOR_VERSION, source=source, latency_ms=latency,
            matched_words=list(decision.matched_words))

    return app


app = create_app()
