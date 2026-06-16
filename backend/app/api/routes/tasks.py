from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.api.schemas.tasks import TaskCreateRequest
from app.core.responses import ok


router = APIRouter(prefix="/api/analysis-tasks", tags=["tasks"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or f"req_{uuid4().hex}"


def _error_response(
    *,
    request: Request,
    status_code: int,
    error_code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "message": message,
            "data": {"error_code": error_code, "message": message},
            "request_id": _request_id(request),
        },
    )


@router.post("")
def create_task(
    payload: TaskCreateRequest,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if not idempotency_key:
        return _error_response(
            request=request,
            status_code=400,
            error_code="IDEMPOTENCY_KEY_REQUIRED",
            message="Idempotency-Key header is required",
        )

    task_service = getattr(request.app.state, "task_service", None)
    if task_service is not None:
        task = task_service.create_task(
            user_id="local-test-user",
            file_id=payload.file_id,
            idempotency_key=idempotency_key,
            options=payload.options,
        )
        return ok(
            {
                "task_id": task.id,
                "file_id": payload.file_id,
                "idempotency_key": idempotency_key,
                "status": task.status,
            },
            request,
        )

    return ok(
        {
            "task_id": f"task_{uuid4().hex}",
            "file_id": payload.file_id,
            "idempotency_key": idempotency_key,
            "status": "queued",
        },
        request,
    )
