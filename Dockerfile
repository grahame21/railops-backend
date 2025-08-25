FROM python:3.10-slim

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app

# Render sets $PORT; default to 10000 for local runs
ENV PORT=10000
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "app:app"]
