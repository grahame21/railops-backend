FROM python:3.12-slim

# minimal base packages
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install Python deps first (for layer cache)
COPY app/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install --with-deps chromium

# app code
COPY app /app

# start (shell form so $PORT expands on Render)
CMD ["sh","-c","gunicorn -b 0.0.0.0:${PORT:-10000} server:app"]
