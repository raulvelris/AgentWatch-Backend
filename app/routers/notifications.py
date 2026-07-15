"""Router de notificaciones — RF22 (Módulo 6).

CA-01 : expone el campo `criticidad` (CRITICAL / WARNING / INFO) en todos
        los endpoints.
CA-02 : el `agent_id` en las notificaciones CRITICAL habilita el deep link
        desde la mobile app.
CA-05 : PATCH /{id}/read sincroniza el estado leída entre mobile y dashboard.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import datetime

from app.core.database import get_session
from app.models import NotificacionDB
from app.services.notificaciones import encolar_notificacion

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["RF22 - Notifications"],
)


class PushNotificationRequest(BaseModel):
    tipo: str  # "promotion_pendiente" | "promotion_expirada" | "deploy_fallido"
    destinatario_rol: str
    mensaje: str
    agent_id: str | None = None
    # RF22 CA-01: nivel explícito; si omitido se infiere del `tipo`
    criticidad: str | None = None  # "CRITICAL" | "WARNING" | "INFO"


def _notif_a_dict(n: NotificacionDB) -> dict:
    """Serializa una NotificacionDB incluyendo `criticidad` (CA-01)."""
    return {
        "id": n.id,
        "tipo": n.tipo,
        "criticidad": n.criticidad,
        "destinatario_rol": n.destinatario_rol,
        "mensaje": n.mensaje,
        "agent_id": n.agent_id,
        "fecha": n.fecha,
        "leida": n.leida,
    }


@router.get("/")
def list_notifications(
    destinatario_rol: str | None = None,
    tipo: str | None = None,
    criticidad: str | None = None,
    agent_id: str | None = None,
):
    """Lista el outbox, filtrable por destinatario_rol, tipo, criticidad y agent_id."""
    with get_session() as session:
        consulta = session.query(NotificacionDB)
        if destinatario_rol is not None:
            consulta = consulta.filter(
                NotificacionDB.destinatario_rol == destinatario_rol
            )
        if tipo is not None:
            consulta = consulta.filter(NotificacionDB.tipo == tipo)
        if criticidad is not None:
            consulta = consulta.filter(
                NotificacionDB.criticidad == criticidad.upper()
            )
        if agent_id is not None:
            consulta = consulta.filter(NotificacionDB.agent_id == agent_id)
        return {
            "notifications": [
                _notif_a_dict(n)
                for n in consulta.order_by(NotificacionDB.id).all()
            ]
        }


@router.patch("/{notification_id}/read")
def mark_as_read(notification_id: int):
    """CA-05: marca una notificación como leída (sincronización mobile ↔ web)."""
    with get_session() as session:
        n = session.query(NotificacionDB).filter(
            NotificacionDB.id == notification_id
        ).first()
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        n.leida = True
        session.commit()
        return {
            "success": True,
            "id": n.id,
            "leida": n.leida,
        }


@router.post("/push")
def send_push_notification(req: PushNotificationRequest):
    """CA-01/CA-03: encola la notificación con su criticidad y despacha a FCM."""
    notif = encolar_notificacion(
        tipo=req.tipo,
        destinatario_rol=req.destinatario_rol,
        mensaje=req.mensaje,
        agent_id=req.agent_id,
        criticidad=req.criticidad,
    )
    return {
        "success": True,
        "notification": _notif_a_dict(notif),
    }
