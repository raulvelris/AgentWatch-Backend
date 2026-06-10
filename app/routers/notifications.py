from fastapi import APIRouter

from app.core.database import get_session
from app.models import NotificacionDB

# Módulo 2 (Despliegue / CI-CD) — RF06: outbox de notificaciones.
# Sustituto etiquetado del email/push real (llega con el Módulo 6): aquí
# solo se consulta lo encolado por promociones y deploys fallidos.
router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Deployment - Notifications"]
)


@router.get("/")
def list_notifications(
    destinatario_rol: str | None = None,
    tipo: str | None = None,
    agent_id: str | None = None,
):
    """Lista el outbox, filtrable por destinatario_rol ("ADMIN"), tipo
    ("promotion_pendiente" | "promotion_expirada" | "deploy_fallido")
    y agent_id."""
    with get_session() as session:
        consulta = session.query(NotificacionDB)
        if destinatario_rol is not None:
            consulta = consulta.filter(
                NotificacionDB.destinatario_rol == destinatario_rol
            )
        if tipo is not None:
            consulta = consulta.filter(NotificacionDB.tipo == tipo)
        if agent_id is not None:
            consulta = consulta.filter(NotificacionDB.agent_id == agent_id)
        return {
            "notifications": [
                {
                    "id": n.id,
                    "tipo": n.tipo,
                    "destinatario_rol": n.destinatario_rol,
                    "mensaje": n.mensaje,
                    "agent_id": n.agent_id,
                    "fecha": n.fecha,
                }
                for n in consulta.order_by(NotificacionDB.id).all()
            ]
        }
