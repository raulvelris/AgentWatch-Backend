from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas.environment import PromoteRequest

# Módulo 2 (Despliegue / CI-CD) — RF06: ambientes dev/staging/prod + promotion.
router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Deployment - Environments"]
)

AMBIENTES = ["dev", "staging", "prod"]

# Historial auditable de promociones (append-only, en memoria).
promotions_db: list[dict] = []


@router.get("/environments")
def list_environments():
    return {"environments": AMBIENTES}


@router.post("/{agent_id}/promote")
def promote(agent_id: str, req: PromoteRequest):
    if req.ambiente_destino not in AMBIENTES or req.ambiente_origen not in AMBIENTES:
        raise HTTPException(status_code=400, detail="Ambiente inválido")

    # RF06: la promoción a prod requiere rol ADMIN.
    # STUB de auth: mientras el Módulo 4 (RF13) no exponga JWT/RBAC, el rol llega
    # en el body. Reemplazar por una dependencia real de auth cuando exista.
    es_admin = req.rol_solicitante.upper() == "ADMIN"
    if req.ambiente_destino == "prod" and not es_admin:
        raise HTTPException(
            status_code=403,
            detail="La promoción a prod requiere aprobación de un usuario con rol ADMIN",
        )

    registro = {
        "agent_id": agent_id,
        "ambiente_origen": req.ambiente_origen,
        "ambiente_destino": req.ambiente_destino,
        "solicitante": req.solicitante,
        "aprobado_por": req.solicitante if es_admin else None,
        "estado": "aprobada" if es_admin else "pendiente",
        "fecha": datetime.now(timezone.utc).isoformat(),
    }
    promotions_db.append(registro)
    return {"ok": True, "promotion": registro}


@router.get("/{agent_id}/promotions")
def list_promotions(agent_id: str):
    return {"promotions": [p for p in promotions_db if p["agent_id"] == agent_id]}
