"""NotificationService — RF22 (Módulo 6): notificaciones push contextuales.

CA-01: 3 niveles de criticidad formales:
  - CRITICAL  → fallo total (deploy_fallido)
  - WARNING   → degradación / budget (promotion_pendiente)
  - INFO      → tarea completada (promotion_expirada y otros)

CA-03: El backend encola en menos de 1 s; la entrega final a FCM
        se despacha de forma asíncrona (simulada con log); el polling
        del mobile cada 5 s garantiza el SLA de 10 s end-to-end.

Integración FCM: en producción, `_despachar_fcm` invoca la API de
Firebase Admin SDK con el token del dispositivo guardado en la DB.
En el prototipo académico se usa un mock que loggea la llamada.
"""

import logging
from datetime import datetime, timezone

from app.core.database import get_session
from app.models import NotificacionDB

logger = logging.getLogger(__name__)

# RF22 CA-01: mapa canónico tipo → criticidad
_TIPO_A_CRITICIDAD: dict[str, str] = {
    "deploy_fallido": "CRITICAL",
    "promotion_pendiente": "WARNING",
    "promotion_expirada": "INFO",
}

# Iconos para el log simulado de FCM (hace visible la categorización)
_ICONO_CRITICIDAD: dict[str, str] = {
    "CRITICAL": "🔴",
    "WARNING":  "🟡",
    "INFO":     "🔵",
}


def _resolver_criticidad(tipo: str, criticidad: str | None) -> str:
    """Devuelve el nivel de criticidad definitivo.

    Si el caller lo pasa explícitamente, ese valor prevalece (permite
    tipos futuros con criticidad personalizada).  Si no, se infiere del
    `tipo` usando el mapa canónico del CA-01.
    """
    if criticidad and criticidad.upper() in ("CRITICAL", "WARNING", "INFO"):
        return criticidad.upper()
    return _TIPO_A_CRITICIDAD.get(tipo, "INFO")


def _despachar_fcm(
    criticidad: str,
    tipo: str,
    mensaje: str,
    agent_id: str | None,
    notif_id: int,
) -> None:
    """Simula el despacho FCM (mock académico).

    En producción reemplazar por:
        firebase_admin.messaging.send(
            firebase_admin.messaging.Message(
                notification=firebase_admin.messaging.Notification(
                    title=f"AgentWatch [{criticidad}]",
                    body=mensaje,
                ),
                data={"agent_id": agent_id or "", "notif_id": str(notif_id)},
                topic=f"agentwatch_{criticidad.lower()}",
            )
        )
    """
    icono = _ICONO_CRITICIDAD.get(criticidad, "🔔")
    logger.info(
        "[FCM-MOCK] %s [%s] tipo=%s agent_id=%s notif_id=%d | %s",
        icono,
        criticidad,
        tipo,
        agent_id,
        notif_id,
        mensaje[:120],
    )


def encolar_notificacion(
    tipo: str,
    destinatario_rol: str,
    mensaje: str,
    agent_id: str | None = None,
    criticidad: str | None = None,
) -> NotificacionDB:
    """Persiste la notificación en el outbox y despacha a FCM (mock).

    Parámetros
    ----------
    tipo            : causa semántica del evento (ej. "deploy_fallido")
    destinatario_rol: rol destino (ej. "ADMIN")
    mensaje         : texto completo con contexto (CA-06)
    agent_id        : ID del agente afectado (habilita deep link CA-02)
    criticidad      : nivel explícito; si None se infiere del `tipo` (CA-01)

    Retorna la instancia `NotificacionDB` recién creada (con id asignado).
    """
    nivel = _resolver_criticidad(tipo, criticidad)

    with get_session() as session:
        notif = NotificacionDB(
            tipo=tipo,
            criticidad=nivel,
            destinatario_rol=destinatario_rol,
            mensaje=mensaje,
            agent_id=agent_id,
            fecha=datetime.now(timezone.utc).isoformat(),
            leida=False,
        )
        session.add(notif)
        session.commit()
        session.refresh(notif)

    # CA-03: despacho FCM inmediato tras persistir (< 1 s)
    _despachar_fcm(nivel, tipo, mensaje, agent_id, notif.id)

    return notif
