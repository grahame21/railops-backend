FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

# Use shell so $PORT expands on Render
CMD ["sh","-c","gunicorn -b 0.0.0.0:${PORT:-10000} server:app"]
