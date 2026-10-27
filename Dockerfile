FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Release version shown on the dashboard's Updates page (the image has no
# .git to ask). Set by the publish workflow; "dev" for local builds.
ARG VERSION=dev
RUN echo "$VERSION" > /app/VERSION

ENV TELEFIN_DOCKER=1 \
    SESSION_NAME=/config/userbot_session \
    DB_PATH=/config/telefin.db \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8420

VOLUME ["/config"]
EXPOSE 8420

CMD ["python", "main.py"]
