"""Outbox de notificaciones (RF06) — Módulo 2.

Sustituto etiquetado del email/push real: el envío llega con el Módulo 6
(canal de notificaciones); mientras tanto el backend ENCOLA en la tabla
`notificaciones` y GET /api/v1/notifications permite consultarlas (y al
front, mostrarlas).
"""

from datetime import datetime, timezone

from app.core.database import get_session
from app.models import NotificacionDB


def encolar_notificacion(
    tipo: str,
    destinatario_rol: str,
    mensaje: str,
    agent_id: str | None = None,
) -> None:
    """Agrega una notificación al outbox.

    tipos usados: "promotion_pendiente" | "promotion_expirada" |
    "deploy_fallido"; destinatario_rol: "ADMIN" (roles del Módulo 4).
    """
    with get_session() as session:
        session.add(
            NotificacionDB(
                tipo=tipo,
                destinatario_rol=destinatario_rol,
                mensaje=mensaje,
                agent_id=agent_id,
                fecha=datetime.now(timezone.utc).isoformat(),
            )
        )
        session.commit()
