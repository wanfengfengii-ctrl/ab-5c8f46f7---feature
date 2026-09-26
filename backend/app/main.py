"""FastAPI application: splice audit service."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .audit import AuditInputError, audit

app = FastAPI(title="岸桥小车导轨拼接曲线审计", version="1.0.0")


@app.get("/health")
@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.post("/api/audit")
def run_audit(payload: Dict[str, Any]) -> JSONResponse:
    try:
        result = audit(payload)
    except AuditInputError as exc:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": {
                "code": "INVALID_INPUT",
                "message": str(exc),
                "segment": None,
                "parameter": None,
                "point": None,
            }},
        )
    return JSONResponse(status_code=200, content=result)
