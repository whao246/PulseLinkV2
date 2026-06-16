FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

WORKDIR /app

COPY backend/requirements.txt /tmp/pulselink-requirements.txt
RUN pip install --no-cache-dir -r /tmp/pulselink-requirements.txt

COPY backend /app/backend

WORKDIR /app/backend
