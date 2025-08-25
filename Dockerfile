# Dockerfile
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements at repo root
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code in /app
COPY app /app

# Default port used by Render for Docker web services is 10000
EXPOSE 10000

# Gunicorn looks for module "app" with attribute "app"
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "app:app"]
