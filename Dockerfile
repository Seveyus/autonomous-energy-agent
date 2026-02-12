FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app
COPY . .

# Cloud Run listens on $PORT
ENV PORT=8080
EXPOSE 8080

# Prod server: gunicorn + uvicorn workers
CMD exec gunicorn -k uvicorn.workers.UvicornWorker -w 2 -t 120 -b 0.0.0.0:${PORT} main:app

