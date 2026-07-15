"""EscalationService — RF24 CA-04: escalación automática de alertas CRITICAL.

Si una alerta CRITICAL no es marcada como leída en 15 minutos, se escala
automáticamente al siguiente responsable configurado en AlertChannelConfigDB.

Implementación: evaluación perezosa (lazy) al consultar el historial — igual
que la expiración de promociones en RF06. No requiere Azure Durable Functions
para el prototipo académico; en producción se reemplazaría por un timer trigger.

Flujo:
  1. GET /api/v1/alerts  →  _escalar_pendientes() verifica CRITICAL sin leer.
  2. Si han pasado > 15 min sin marcar como leída → estado = "escalada".
  3. El AlertDispatcher notifica al `escalation_contact` por email/push.
  4. La alerta original queda registrada con `escalado_a` y `escalado_en`.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import get_session
from app.models import AlertDB, AlertChannelConfigDB

logger = logging.getLogger(__name__)

ESCALATION_TIMEOUT = timedelta(minutes=15)  # CA-04: 15 minutos


def _obtener_contacto_escalacion(tenant_id: str) -> str | None:
    """Recupera el email/ID del siguiente responsable para el tenant."""
    with get_session() as session:
        config = (
            session.query(AlertChannelConfigDB)
            .filter(
                AlertChannelConfigDB.tenant_id == tenant_id,
                AlertChannelConfigDB.criticidad == "CRITICAL",
            )
            .first()
        )
        return config.escalation_contact if config else None


def _notificar_escalacion(alert: AlertDB, contacto: str) -> None:
    """Envía la notificación de escalación al siguiente responsable."""
    from app.services.notificaciones import encolar_notificacion
    encolar_notificacion(
        tipo="escalacion_critica",
        destinatario_rol="ADMIN",
        mensaje=(
            f"ESCALACIÓN AUTOMÁTICA — Alerta #{alert.id} no fue atendida en 15 min. "
            f"Tipo: {alert.tipo} | Agente: {alert.agent_id or 'N/A'} | "
            f"Contacto escalado: {contacto} | Mensaje: {alert.mensaje[:100]}"
        ),
        agent_id=alert.agent_id,
        criticidad="CRITICAL",
    )
    logger.info(
        "[Escalation] Alerta #%d escalada a '%s' (tenant=%s)",
        alert.id, contacto, alert.tenant_id,
    )


def escalar_pendientes() -> list[int]:
    """Evalúa alertas CRITICAL sin leer que superaron el timeout de 15 min.

    Retorna lista de IDs de alertas recién escaladas.
    Diseño lazy: se llama en cada GET /api/v1/alerts (sin scheduler externo).
    """
    limite = datetime.now(timezone.utc) - ESCALATION_TIMEOUT
    escaladas_ids = []

    with get_session() as session:
        candidatas = (
            session.query(AlertDB)
            .filter(
                AlertDB.criticidad == "CRITICAL",
                AlertDB.estado == "pendiente",
                AlertDB.fecha <= limite.isoformat(),
            )
            .all()
        )

        for alert in candidatas:
            contacto = _obtener_contacto_escalacion(alert.tenant_id)
            alert.estado = "escalada"
            alert.escalado_en = datetime.now(timezone.utc).isoformat()
            alert.escalado_a = contacto or "admin@agentwatch.app"
            escaladas_ids.append(alert.id)

        if candidatas:
            session.commit()

    for alert_id in escaladas_ids:
        with get_session() as session:
            alert = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
            if alert:
                _notificar_escalacion(alert, alert.escalado_a)

    return escaladas_ids
