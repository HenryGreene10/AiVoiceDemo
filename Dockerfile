FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# default envs (can be overridden by the platform)
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000

# Gunicorn + Uvicorn workers for prod
CMD ["bash","-lc","gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:${PORT} main:app"]
