FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN addgroup --system archpilot && adduser --system --ingroup archpilot archpilot

COPY pyproject.toml ./
COPY app ./app
RUN python -m pip install --no-cache-dir .

USER archpilot
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=8s --start-period=30s --retries=4 \
    CMD ["python", "-m", "app.container_health"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
