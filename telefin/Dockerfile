FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SESSION_NAME=/config/userbot_session \
    DB_PATH=/config/telefin.db \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8420

VOLUME ["/config"]
EXPOSE 8420

CMD ["python", "main.py"]
