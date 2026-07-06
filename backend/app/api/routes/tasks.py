from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from app.api.dependencies.auth import get_current_user_id
from app.api.schemas.tasks import TaskCreateRequest
from app.application.task_service import TaskService
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
    user_id: str = Depends(get_current_user_id),
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
            user_id=user_id,
            file_id=payload.file_id,
            idempotency_key=idempotency_key,
            options=payload.options,
        )
        return ok(
            {
                "task_id": task.id,
                "task": {
                    "id": task.id,
                    "status": task.status,
                    "file_id": payload.file_id,
                },
                "file_id": payload.file_id,
                "idempotency_key": idempotency_key,
                "status": task.status,
            },
            request,
        )

    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError("database is not configured")

    db_session = session_factory()
    try:
        task = TaskService(
            db_session=db_session,
            queue_publisher=getattr(request.app.state, "queue_publisher", None),
        ).create_task(
            user_id=user_id,
            file_id=payload.file_id,
            idempotency_key=idempotency_key,
            options=payload.options,
        )
    finally:
        db_session.close()

    return ok(
        {
            "task_id": task.id,
            "task": {
                "id": task.id,
                "status": task.status,
                "file_id": payload.file_id,
            },
            "file_id": payload.file_id,
            "idempotency_key": idempotency_key,
            "status": task.status,
        },
        request,
    )


@router.get("/{task_id}")
def get_task(
    task_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    task_service = getattr(request.app.state, "task_service", None)
    if task_service is not None and hasattr(task_service, "get_task"):
        task = task_service.get_task(task_id)
        if task is None or task.user_id != user_id:
            return _error_response(
                request=request,
                status_code=404,
                error_code="TASK_NOT_FOUND",
                message="analysis task not found",
            )
        steps = task_service.list_steps(task_id)
        return ok(_task_detail_payload(task, steps), request)

    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError("database is not configured")

    db_session = session_factory()
    try:
        service = TaskService(
            db_session=db_session,
            queue_publisher=getattr(request.app.state, "queue_publisher", None),
        )
        task = service.get_task(task_id)
        if task is None or task.user_id != user_id:
            return _error_response(
                request=request,
                status_code=404,
                error_code="TASK_NOT_FOUND",
                message="analysis task not found",
            )
        steps = service.list_steps(task_id)
        return ok(_task_detail_payload(task, steps), request)
    finally:
        db_session.close()


def _task_detail_payload(task, steps) -> dict:
    return {
        "task_id": task.id,
        "task": {
            "id": task.id,
            "user_id": task.user_id,
            "file_id": task.file_id,
            "status": task.status,
            "task_type": task.task_type,
            "model_profile": task.model_profile,
            "idempotency_key": task.idempotency_key,
            "error_message": task.error_message,
            "payload": task.payload or {},
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        },
        "steps": [
            {
                "id": step.id,
                "step_name": step.step_name,
                "status": step.status,
                "attempt_count": step.attempt_count,
                "max_attempts": step.max_attempts,
                "error_code": step.error_code,
                "error_message": step.error_message,
                "payload": step.payload or {},
                "started_at": step.started_at,
                "completed_at": step.completed_at,
            }
            for step in steps
        ],
    }
