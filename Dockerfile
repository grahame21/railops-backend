FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Australia/Adelaide

WORKDIR /app
COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY app /app

EXPOSE 10000
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "app:app"]
