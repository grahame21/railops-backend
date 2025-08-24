# ✅ Uses Playwright image with browsers preinstalled
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app
COPY app/requirements.txt /app/

# Flask/gunicorn/requests; playwright already present in this image
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

ENV PORT=10000
EXPOSE 10000
CMD ["bash","-lc","gunicorn -w 1 -b 0.0.0.0:${PORT} server:app --timeout 120"]