FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi \
    httpx \
    pymysql \
    pydantic \
    redis \
    rq \
    sqlalchemy \
    uvicorn

COPY backend /app/backend

WORKDIR /app/backend
