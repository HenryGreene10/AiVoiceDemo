# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1

# Start the FastAPI app with gunicorn/uvicorn.
# Use shell form so $PORT expands on Render. Default to 10000 locally.
CMD sh -c 'gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-10000} src.app:app'
