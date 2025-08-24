# Includes Python, Playwright 1.45, Chromium, and all OS deps preinstalled
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install your Python deps (you can keep playwright==1.45.0 in requirements or remove it)
COPY app/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app /app

# Start (shell form so $PORT expands on Render)
CMD ["sh","-c","gunicorn -b 0.0.0.0:${PORT:-10000} server:app"]
