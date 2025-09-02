# Simple Dockerfile for the web service
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps (requirements.txt must be at repo root)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the app package
COPY app /app

# Render sets $PORT. Default to 10000 locally.
ENV PORT=10000
EXPOSE 10000

# Run via gunicorn; the Flask app object is in server.py
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "server:app"]
