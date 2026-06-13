from __future__ import annotations

from uuid import uuid4

from fastapi import Request


def ok(data: dict, request: Request) -> dict:
    request_id = request.headers.get("X-Request-Id") or f"req_{uuid4().hex}"
    return {
        "code": 0,
        "message": "ok",
        "data": data,
        "request_id": request_id,
    }
