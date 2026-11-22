FROM python:3.11-slim AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY --from=dependencies /install /usr/local
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY --chown=10001:10001 src/ ./src/
COPY --chown=10001:10001 artifacts/preprocessor.joblib artifacts/manifest.json ./artifacts/
COPY --chown=10001:10001 models/model.joblib ./models/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--log-config", "src/logging.json"]
