FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ✅ copy the requirements file that lives under app/
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy the rest of the app code
COPY app /app

EXPOSE 10000
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "app:app"]
