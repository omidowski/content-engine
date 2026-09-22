FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .
RUN useradd --create-home studio && mkdir -p /data/output && chown -R studio:studio /data
USER studio
ENV APP_ENV=production DATABASE_URL=sqlite:////data/content.db OUTPUT_DIR=/data/output ALLOW_DEMO_FALLBACK=false
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
