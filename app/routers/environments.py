from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_session
from app.models import PromotionDB
from app.schemas.environment import PromoteRequest
from app.services import reloj
from app.services.deps import get_current_claims
from app.services.governance_service import evaluar_gate_promocion
from app.services.notificaciones import encolar_notificacion

# Módulo 2 (Despliegue / CI-CD) — RF06: ambientes dev/staging/prod + promotion.
router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Deployment - Environments"]
)

AMBIENTES = ["dev", "staging", "prod"]

# RF06: una solicitud pendiente que nadie aprueba expira a las 24h.
# La expiración se evalúa de forma perezosa al consultar (no hay scheduler
# en el prototipo); reloj.ahora_utc es inyectable para testearla.
EXPIRACION = timedelta(hours=24)


def _a_dict(p: PromotionDB) -> dict:
    # Mismas claves que el registro original en memoria: el front y los
    # tests existentes consumen exactamente esta forma.
    return {
        "agent_id": p.agent_id,
        "ambiente_origen": p.ambiente_origen,
        "ambiente_destino": p.ambiente_destino,
        "solicitante": p.solicitante,
        "aprobado_por": p.aprobado_por,
        "estado": p.estado,
        "fecha": p.fecha,
    }


def _expirar_pendientes(session) -> list[PromotionDB]:
    """Marca 'expirada' toda promoción 'pendiente' con más de 24h y devuelve
    las recién expiradas (para encolar su notificación)."""
    limite = reloj.ahora_utc() - EXPIRACION
    expiradas = []
    pendientes = (
        session.query(PromotionDB).filter(PromotionDB.estado == "pendiente").all()
    )
    for p in pendientes:
        if datetime.fromisoformat(p.fecha) <= limite:
            p.estado = "expirada"
            expiradas.append(p)
    if expiradas:
        session.commit()
    return expiradas


def _notificar_expiradas(expiradas: list[PromotionDB]) -> None:
    for p in expiradas:
        encolar_notificacion(
            "promotion_expirada",
            "ADMIN",
            f"La solicitud de promoción de {p.agent_id} "
            f"({p.ambiente_origen} -> {p.ambiente_destino}) de {p.solicitante} "
            f"expiró sin aprobación (24h).",
            agent_id=p.agent_id,
        )


@router.get("/environments")
def list_environments():
    return {"environments": AMBIENTES}


@router.post("/{agent_id}/promote")
def promote(
    agent_id: str,
    req: PromoteRequest,
    claims: dict | None = Depends(get_current_claims),
):
    if req.ambiente_destino not in AMBIENTES or req.ambiente_origen not in AMBIENTES:
        raise HTTPException(status_code=400, detail="Ambiente inválido")

    # RF06: la promoción a prod requiere rol ADMIN.
    # Identidad: el JWT del Módulo 4 (header Authorization: Bearer) tiene
    # precedencia; con token, rol y solicitante salen de los claims.
    # FALLBACK TEMPORAL documentado: sin token, el rol llega en el body
    # (rol_solicitante) — el front actual y 5 tests existentes dependen de
    # ese stub; se retira cuando el front envíe el token (RF13, Módulo 4).
    if claims is not None:
        rol = claims.get("rol", "")
        solicitante = claims.get("sub", req.solicitante)
    else:
        rol = req.rol_solicitante
        solicitante = req.solicitante
    es_admin = rol.upper() == "ADMIN"
    if req.ambiente_destino == "prod" and not es_admin:
        raise HTTPException(
            status_code=403,
            detail="La promoción a prod requiere aprobación de un usuario con rol ADMIN",
        )

    # Release gate de calidad (MLOps, ver docs/plan-mlops-release-gate.md):
    # además del rol, la promoción a prod debe superar las políticas
    # `release_gate` activas del tenant (tasa de éxito de los últimos N
    # despliegues). Bloqueo duro: aplica también a un ADMIN. 409 y no 403:
    # la identidad es válida; lo que falla es el estado de calidad del
    # agente. Sin políticas activas, el flujo es idéntico al anterior.
    # tenant: claim del JWT si hay token; sin token, mismo default que
    # AgentConfig.tenant_id (las tablas del Módulo 2 no llevan tenant_id).
    if req.ambiente_destino == "prod":
        tenant_id = claims.get("tenant", "tenant_a") if claims else "tenant_a"
        aprobado, motivo = evaluar_gate_promocion(tenant_id, agent_id)
        if not aprobado:
            raise HTTPException(status_code=409, detail=motivo)

    registro = PromotionDB(
        agent_id=agent_id,
        ambiente_origen=req.ambiente_origen,
        ambiente_destino=req.ambiente_destino,
        solicitante=solicitante,
        aprobado_por=solicitante if es_admin else None,
        estado="aprobada" if es_admin else "pendiente",
        fecha=reloj.ahora_utc().isoformat(),
    )
    with get_session() as session:
        session.add(registro)
        session.commit()
        respuesta = _a_dict(registro)

    if registro.estado == "pendiente":
        # RF06: el Admin debe enterarse de la solicitud. Outbox como
        # sustituto del email/push (Módulo 6).
        encolar_notificacion(
            "promotion_pendiente",
            "ADMIN",
            f"Promoción de {agent_id} ({req.ambiente_origen} -> "
            f"{req.ambiente_destino}) solicitada por {solicitante}; "
            f"espera aprobación (expira en 24h).",
            agent_id=agent_id,
        )

    return {"ok": True, "promotion": respuesta}


@router.get("/{agent_id}/promotions")
def list_promotions(agent_id: str):
    with get_session() as session:
        expiradas = _expirar_pendientes(session)
        promociones = (
            session.query(PromotionDB)
            .filter(PromotionDB.agent_id == agent_id)
            .order_by(PromotionDB.id)
            .all()
        )
        resultado = [_a_dict(p) for p in promociones]
    _notificar_expiradas(expiradas)
    return {"promotions": resultado}
