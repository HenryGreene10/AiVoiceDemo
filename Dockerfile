FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Gunicorn + Uvicorn workers for prod
CMD ["sh","-lc","gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT src.app:app"]
