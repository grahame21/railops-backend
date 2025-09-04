FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app

ENV PORT=10000
EXPOSE 10000

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "server:app"]
