FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 quizspark \
    && useradd --uid 10001 --gid quizspark --no-create-home --shell /usr/sbin/nologin quizspark \
    && mkdir -p /app/data/uploads /app/data/imports \
    && chown -R quizspark:quizspark /app/data

COPY --chown=quizspark:quizspark app/ ./
USER 10001:10001
EXPOSE 8080
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"
CMD ["python", "server.py"]
