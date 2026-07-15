"""AlertDispatcher — RF24 CA-01/CA-03: patrón Abstract Factory por canal.

Canales soportados: push móvil, email, Slack, webhook personalizado.

Cada canal implementa la interfaz `ChannelDispatcher`. El `AlertDispatcher`
orquesta el despacho a los canales configurados por el tenant según el nivel
de criticidad (CA-03).

En producción:
  - PushChannelDispatcher  → Firebase Admin SDK (ya integrado en RF22)
  - EmailChannelDispatcher → SendGrid / Azure Communication Services
  - SlackChannelDispatcher → Slack Web API con Block Kit
  - WebhookChannelDispatcher → HTTP POST al endpoint configurado
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# ─── Interfaz abstracta (Abstract Factory) ───────────────────────────────────

class ChannelDispatcher(ABC):
    """Contrato común para todos los canales de alerta."""

    @abstractmethod
    def dispatch(
        self,
        criticidad: str,
        tipo: str,
        mensaje: str,
        agent_id: str | None,
        alert_id: int,
        tenant_id: str,
    ) -> bool:
        """Envía la alerta. Retorna True si fue exitoso."""
        ...

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Identificador del canal (ej. 'push', 'slack')."""
        ...


# ─── Canal: Push Móvil ───────────────────────────────────────────────────────

class PushChannelDispatcher(ChannelDispatcher):
    """CA-01: despacho a notificación push (FCM via RF22)."""

    @property
    def nombre(self) -> str:
        return "push"

    def dispatch(self, criticidad, tipo, mensaje, agent_id, alert_id, tenant_id) -> bool:
        # Reutiliza el outbox de RF22 para no duplicar lógica FCM
        from app.services.notificaciones import encolar_notificacion
        try:
            encolar_notificacion(
                tipo=tipo,
                destinatario_rol="ADMIN",
                mensaje=mensaje,
                agent_id=agent_id,
                criticidad=criticidad,
            )
            logger.info("[PUSH] ✅ alert_id=%d criticidad=%s", alert_id, criticidad)
            return True
        except Exception as exc:
            logger.error("[PUSH] ❌ alert_id=%d error=%s", alert_id, exc)
            return False


# ─── Canal: Email ────────────────────────────────────────────────────────────

class EmailChannelDispatcher(ChannelDispatcher):
    """CA-01: despacho por email (mock académico; producción: SendGrid/Azure)."""

    @property
    def nombre(self) -> str:
        return "email"

    def dispatch(self, criticidad, tipo, mensaje, agent_id, alert_id, tenant_id) -> bool:
        # Mock: en producción invocar SendGrid API
        icono = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(criticidad, "🔔")
        logger.info(
            "[EMAIL-MOCK] %s Enviando email | tenant=%s alert_id=%d tipo=%s | %s",
            icono, tenant_id, alert_id, tipo, mensaje[:100],
        )
        # Payload que iría a SendGrid:
        # {
        #   "to": "admin@tenant.com",
        #   "subject": f"[AgentWatch {criticidad}] {tipo}",
        #   "text": mensaje,
        # }
        return True


# ─── Canal: Slack ────────────────────────────────────────────────────────────

class SlackChannelDispatcher(ChannelDispatcher):
    """CA-01: despacho a Slack con Block Kit (mock si no hay webhook configurado).

    En producción, configurar `slack_webhook_url` en AlertChannelConfigDB.
    """

    def __init__(self, webhook_url: str | None = None):
        self._webhook_url = webhook_url

    @property
    def nombre(self) -> str:
        return "slack"

    def _build_blocks(
        self, criticidad: str, tipo: str, mensaje: str, agent_id: str | None, alert_id: int
    ) -> list:
        """Construye Slack Block Kit con botón de acción."""
        color = {"CRITICAL": "#EF4444", "WARNING": "#FACC15", "INFO": "#38BDF8"}.get(
            criticidad, "#6B7280"
        )
        emoji = {"CRITICAL": ":red_circle:", "WARNING": ":yellow_circle:", "INFO": ":blue_circle:"}.get(
            criticidad, ":bell:"
        )
        return [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} [{criticidad}] AgentWatch Alert"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Tipo:*\n{tipo}"},
                    {"type": "mrkdwn", "text": f"*Agente:*\n{agent_id or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Alert ID:*\n#{alert_id}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Hora:*\n{datetime.now(timezone.utc).strftime('%H:%M UTC')}",
                    },
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"```{mensaje}```"}},
        ]

    def dispatch(self, criticidad, tipo, mensaje, agent_id, alert_id, tenant_id) -> bool:
        blocks = self._build_blocks(criticidad, tipo, mensaje, agent_id, alert_id)
        payload = {"blocks": blocks}

        if self._webhook_url:
            try:
                resp = httpx.post(self._webhook_url, json=payload, timeout=5)
                ok = resp.status_code == 200
                logger.info("[SLACK] alert_id=%d status=%d", alert_id, resp.status_code)
                return ok
            except Exception as exc:
                logger.error("[SLACK] ❌ alert_id=%d error=%s", alert_id, exc)
                return False
        else:
            # Mock: loggea el payload como si se enviara
            logger.info(
                "[SLACK-MOCK] ✅ alert_id=%d tenant=%s | blocks=%s",
                alert_id, tenant_id, json.dumps(blocks, ensure_ascii=False)[:200],
            )
            return True


# ─── Canal: Webhook personalizado ────────────────────────────────────────────

class WebhookChannelDispatcher(ChannelDispatcher):
    """CA-01: HTTP POST al webhook configurado por el tenant."""

    def __init__(self, webhook_url: str | None = None):
        self._webhook_url = webhook_url

    @property
    def nombre(self) -> str:
        return "webhook"

    def dispatch(self, criticidad, tipo, mensaje, agent_id, alert_id, tenant_id) -> bool:
        payload = {
            "source": "agentwatch",
            "alert_id": alert_id,
            "tenant_id": tenant_id,
            "criticidad": criticidad,
            "tipo": tipo,
            "mensaje": mensaje,
            "agent_id": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self._webhook_url:
            try:
                resp = httpx.post(self._webhook_url, json=payload, timeout=5)
                ok = resp.status_code < 400
                logger.info("[WEBHOOK] alert_id=%d url=%s status=%d", alert_id, self._webhook_url, resp.status_code)
                return ok
            except Exception as exc:
                logger.error("[WEBHOOK] ❌ alert_id=%d error=%s", alert_id, exc)
                return False
        else:
            logger.info("[WEBHOOK-MOCK] ✅ alert_id=%d payload=%s", alert_id, json.dumps(payload)[:200])
            return True


# ─── Fábrica de dispatchers ───────────────────────────────────────────────────

_CANAL_A_CLASE: dict[str, type[ChannelDispatcher]] = {
    "push":    PushChannelDispatcher,
    "email":   EmailChannelDispatcher,
    "slack":   SlackChannelDispatcher,
    "webhook": WebhookChannelDispatcher,
}

CANALES_VALIDOS = list(_CANAL_A_CLASE.keys())


def crear_dispatcher(
    canal: str,
    webhook_url: str | None = None,
    slack_webhook_url: str | None = None,
) -> ChannelDispatcher:
    """Factory: instancia el dispatcher correcto para el canal solicitado."""
    clase = _CANAL_A_CLASE.get(canal)
    if clase is None:
        raise ValueError(f"Canal '{canal}' no soportado. Usar: {CANALES_VALIDOS}")
    if canal == "slack":
        return SlackChannelDispatcher(webhook_url=slack_webhook_url)
    if canal == "webhook":
        return WebhookChannelDispatcher(webhook_url=webhook_url)
    return clase()


# ─── AlertDispatcher: orquestador ────────────────────────────────────────────

class AlertDispatcher:
    """CA-03: despacha una alerta a los canales configurados por el tenant/criticidad.

    Uso:
        dispatcher = AlertDispatcher.para_tenant(tenant_id, criticidad)
        resultados = dispatcher.dispatch_todos(alert)
    """

    def __init__(self, dispatchers: list[ChannelDispatcher]):
        self._dispatchers = dispatchers

    @classmethod
    def para_tenant(cls, tenant_id: str, criticidad: str) -> "AlertDispatcher":
        """Construye el dispatcher según la configuración del tenant (CA-03)."""
        from app.core.database import get_session
        from app.models import AlertChannelConfigDB

        with get_session() as session:
            config = (
                session.query(AlertChannelConfigDB)
                .filter(
                    AlertChannelConfigDB.tenant_id == tenant_id,
                    AlertChannelConfigDB.criticidad == criticidad,
                )
                .first()
            )

        if config:
            canales = json.loads(config.canales)
            dsp_list = [
                crear_dispatcher(
                    c,
                    webhook_url=config.webhook_url,
                    slack_webhook_url=config.slack_webhook_url,
                )
                for c in canales
            ]
        else:
            # Defaults: CRITICAL→push+email, WARNING→push, INFO→push
            defaults = {
                "CRITICAL": ["push", "email"],
                "WARNING":  ["push"],
                "INFO":     ["push"],
            }
            dsp_list = [crear_dispatcher(c) for c in defaults.get(criticidad, ["push"])]

        return cls(dsp_list)

    def dispatch_todos(
        self,
        criticidad: str,
        tipo: str,
        mensaje: str,
        agent_id: str | None,
        alert_id: int,
        tenant_id: str,
    ) -> list[str]:
        """Despacha a todos los canales. Retorna lista de canales exitosos."""
        exitosos = []
        for dsp in self._dispatchers:
            ok = dsp.dispatch(criticidad, tipo, mensaje, agent_id, alert_id, tenant_id)
            if ok:
                exitosos.append(dsp.nombre)
        return exitosos
