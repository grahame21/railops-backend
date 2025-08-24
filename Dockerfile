FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

# (optional) avoid python buffering in logs
ENV PYTHONUNBUFFERED=1

# IMPORTANT: shell form so $PORT expands on Render
CMD gunicorn -w 1 -b 0.0.0.0:$PORT app:app --timeout 120 --graceful-timeout 30