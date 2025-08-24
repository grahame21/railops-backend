# ---- Dockerfile ----
FROM python:3.12-slim

# Base OS packages (fonts + CA certs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-unifont \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt \
 && python -m playwright install --with-deps chromium

COPY app /app

# Render provides $PORT; default to 10000 if missing
ENV PORT=10000
EXPOSE 10000
CMD ["bash", "-lc", "gunicorn -w 1 -b 0.0.0.0:${PORT} server:app --timeout 120"]