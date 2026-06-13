from __future__ import annotations

from fastapi import Request


def ok(data: dict, request: Request) -> dict:
    return {"data": data}
