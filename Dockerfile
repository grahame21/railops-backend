FROM python:3.10-slim

# run from /app
WORKDIR /app

# install deps
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# copy your code folder named 'app' into /app
COPY app /app

# helpful to see what's actually inside the image (can remove later)
RUN echo "==== LIST /app ====" && ls -la /app

# Render injects $PORT; shell-form CMD lets it expand
CMD gunicorn -w 1 -b 0.0.0.0:$PORT app:app --timeout 120 --graceful-timeout 30