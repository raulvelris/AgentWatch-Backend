from fastapi import APIRouter
from app.schemas.audit import AuditLog

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["Audit"]
)

audit_db = []


@router.post("/")
def create_log(log: AuditLog):

    audit_db.append(log)

    return {
        "message": "Log registrado",
        "log": log
    }


@router.get("/")
def list_logs():

    return {
        "logs": audit_db
    }


@router.get("/tenant/{tenant_id}")
def get_tenant_logs(tenant_id: str):

    logs = [
        log for log in audit_db
        if log.tenant_id == tenant_id
    ]

    return {
        "tenant": tenant_id,
        "logs": logs
    }

@router.get("/tenant/{tenant_id}/logs-vulnerable")
def get_logs_vulnerable(tenant_id: str):

    return {
        "tenant": tenant_id,
        "logs": audit_db
    }