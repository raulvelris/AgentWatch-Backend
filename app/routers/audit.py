from fastapi import APIRouter
from app.schemas.audit import AuditLog

# Prefijo movido de /api/v1/audit a /api/v1/security/logs: /api/v1/audit
# pertenece al audit trail del Módulo 5 (RF18, hash chain) y ambos routers
# colisionaban en GET / y POST / (FastAPI atiende el primero registrado y
# el otro queda muerto en silencio). La lógica no cambia.
router = APIRouter(
    prefix="/api/v1/security/logs",
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