"""Router de alertas multicanal — RF24 (Módulo 6).

CA-01 : despacho a 4 canales (push, email, Slack, webhook)
CA-02 : detección automática de anomalías (error_rate, degradación, tokens)
CA-03 : configuración de canales por tenant y criticidad
CA-04 : escalación automática si CRITICAL no se lee en 15 min (lazy eval)
CA-05 : snooze por 1h / 4h / 24h
CA-06 : historial consultable con filtros por canal, criticidad y estado
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import get_session
from app.models import AlertDB, AlertChannelConfigDB
from app.services.alert_dispatcher import AlertDispatcher, CANALES_VALIDOS
from app.services.anomaly_detector import detectar_anomalias
from app.services.escalation_service import escalar_pendientes

router = APIRouter(prefix="/api/v1/alerts", tags=["RF24 - Alerts"])

# ─── Schemas ──────────────────────────────────────────────────────────────────

class CreateAlertRequest(BaseModel):
    tenant_id: str = "tenant_a"
    agent_id: str | None = None
    tipo: str
    criticidad: Literal["CRITICAL", "WARNING", "INFO"]
    mensaje: str


class SnoozeRequest(BaseModel):
    horas: Literal[1, 4, 24]


class ChannelConfigRequest(BaseModel):
    canales: list[str]                  # subset de CANALES_VALIDOS
    webhook_url: str | None = None
    slack_webhook_url: str | None = None
    escalation_contact: str | None = None


class DetectAnomaliesRequest(BaseModel):
    agent_id: str | None = None
    consumo_tokens_actual: float | None = None
    promedio_tokens_historico: float | None = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _alert_a_dict(a: AlertDB) -> dict:
    return {
        "id": a.id,
        "tenant_id": a.tenant_id,
        "agent_id": a.agent_id,
        "tipo": a.tipo,
        "criticidad": a.criticidad,
        "mensaje": a.mensaje,
        "canales_usados": json.loads(a.canales_usados or "[]"),
        "estado": a.estado,
        "snooze_until": a.snooze_until,
        "escalado_a": a.escalado_a,
        "escalado_en": a.escalado_en,
        "fecha": a.fecha,
    }


def _crear_y_despachar(
    tenant_id: str,
    agent_id: str | None,
    tipo: str,
    criticidad: str,
    mensaje: str,
) -> AlertDB:
    """Persiste la alerta y la despacha por los canales configurados."""
    now = datetime.now(timezone.utc).isoformat()

    with get_session() as session:
        alert = AlertDB(
            tenant_id=tenant_id,
            agent_id=agent_id,
            tipo=tipo,
            criticidad=criticidad,
            mensaje=mensaje,
            canales_usados="[]",
            estado="pendiente",
            fecha=now,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        alert_id = alert.id

    # Despachar a canales configurados (CA-01/CA-03)
    dispatcher = AlertDispatcher.para_tenant(tenant_id, criticidad)
    canales_exitosos = dispatcher.dispatch_todos(
        criticidad=criticidad,
        tipo=tipo,
        mensaje=mensaje,
        agent_id=agent_id,
        alert_id=alert_id,
        tenant_id=tenant_id,
    )

    # Actualizar canales usados en la alerta
    with get_session() as session:
        alert = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
        alert.canales_usados = json.dumps(canales_exitosos)
        session.commit()
        session.refresh(alert)

    return alert


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/")
def list_alerts(
    tenant_id: str | None = None,
    criticidad: str | None = None,
    estado: str | None = None,
    canal: str | None = None,
    agent_id: str | None = None,
):
    """CA-06: historial de alertas con filtros + evaluación perezosa de escalación.

    Filtros disponibles: tenant_id, criticidad, estado, canal, agent_id.
    `estado` acepta: pendiente | leida | snoozed | escalada.
    `canal`  filtra alerts que usaron ese canal (push/email/slack/webhook).
    """
    # CA-04: evaluar escalaciones antes de responder
    escalar_pendientes()

    with get_session() as session:
        q = session.query(AlertDB)
        if tenant_id:
            q = q.filter(AlertDB.tenant_id == tenant_id)
        if criticidad:
            q = q.filter(AlertDB.criticidad == criticidad.upper())
        if estado:
            q = q.filter(AlertDB.estado == estado)
        if agent_id:
            q = q.filter(AlertDB.agent_id == agent_id)

        alerts = q.order_by(AlertDB.id.desc()).all()

    # Filtrado por canal en Python (canales_usados es JSON)
    if canal:
        alerts = [a for a in alerts if canal in json.loads(a.canales_usados or "[]")]

    # Recalcular snooze expirado (lazy)
    now_iso = datetime.now(timezone.utc).isoformat()
    resultado = []
    with get_session() as session:
        for a in alerts:
            if a.estado == "snoozed" and a.snooze_until and a.snooze_until <= now_iso:
                db_a = session.query(AlertDB).filter(AlertDB.id == a.id).first()
                if db_a:
                    db_a.estado = "pendiente"
                    db_a.snooze_until = None
                    session.commit()
                    session.refresh(db_a)
                    a = db_a
            resultado.append(_alert_a_dict(a))

    return {"alerts": resultado, "total": len(resultado)}


@router.post("/")
def create_alert(req: CreateAlertRequest):
    """Crea y despacha una alerta a los canales configurados (CA-01/CA-03)."""
    alert = _crear_y_despachar(
        tenant_id=req.tenant_id,
        agent_id=req.agent_id,
        tipo=req.tipo,
        criticidad=req.criticidad,
        mensaje=req.mensaje,
    )
    return {"success": True, "alert": _alert_a_dict(alert)}


@router.post("/detect")
def detect_anomalies(req: DetectAnomaliesRequest):
    """CA-02: dispara el AnomalyDetector y crea alertas por las anomalías encontradas.

    Ideal para ser llamado periódicamente por un scheduler o manualmente.
    """
    anomalias = detectar_anomalias(
        agent_id=req.agent_id,
        consumo_tokens_actual=req.consumo_tokens_actual,
        promedio_tokens_historico=req.promedio_tokens_historico,
    )

    creadas = []
    for anomalia in anomalias:
        alert = _crear_y_despachar(
            tenant_id="tenant_a",
            agent_id=anomalia.agent_id,
            tipo=anomalia.tipo,
            criticidad=anomalia.criticidad,
            mensaje=anomalia.mensaje,
        )
        creadas.append(_alert_a_dict(alert))

    return {
        "anomalias_detectadas": len(creadas),
        "alerts": creadas,
    }


@router.patch("/{alert_id}/read")
def mark_alert_read(alert_id: int):
    """CA-05/CA-06: marca la alerta como leída, cancela escalación pendiente."""
    with get_session() as session:
        alert = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alerta no encontrada")
        alert.estado = "leida"
        alert.snooze_until = None
        session.commit()
        return {"success": True, "alert": _alert_a_dict(alert)}


@router.post("/{alert_id}/snooze")
def snooze_alert(alert_id: int, req: SnoozeRequest):
    """CA-05: silencia la alerta por 1h, 4h o 24h configurable."""
    with get_session() as session:
        alert = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alerta no encontrada")
        snooze_until = datetime.now(timezone.utc) + timedelta(hours=req.horas)
        alert.estado = "snoozed"
        alert.snooze_until = snooze_until.isoformat()
        session.commit()
        return {
            "success": True,
            "alert": _alert_a_dict(alert),
            "snooze_until": alert.snooze_until,
        }


# ─── Configuración de canales por tenant (CA-03) ─────────────────────────────

@router.get("/config/{tenant_id}")
def get_channel_config(tenant_id: str):
    """CA-03: obtiene la configuración de canales del tenant por criticidad."""
    with get_session() as session:
        configs = (
            session.query(AlertChannelConfigDB)
            .filter(AlertChannelConfigDB.tenant_id == tenant_id)
            .all()
        )
    return {
        "tenant_id": tenant_id,
        "config": [
            {
                "criticidad": c.criticidad,
                "canales": json.loads(c.canales),
                "webhook_url": c.webhook_url,
                "slack_webhook_url": c.slack_webhook_url,
                "escalation_contact": c.escalation_contact,
            }
            for c in configs
        ],
    }


@router.put("/config/{tenant_id}/{criticidad}")
def upsert_channel_config(
    tenant_id: str,
    criticidad: Literal["CRITICAL", "WARNING", "INFO"],
    req: ChannelConfigRequest,
):
    """CA-03: crea o actualiza la configuración de canales para un tenant/criticidad."""
    canales_invalidos = [c for c in req.canales if c not in CANALES_VALIDOS]
    if canales_invalidos:
        raise HTTPException(
            status_code=400,
            detail=f"Canales inválidos: {canales_invalidos}. Válidos: {CANALES_VALIDOS}",
        )

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
            config.canales = json.dumps(req.canales)
            config.webhook_url = req.webhook_url
            config.slack_webhook_url = req.slack_webhook_url
            config.escalation_contact = req.escalation_contact
        else:
            config = AlertChannelConfigDB(
                tenant_id=tenant_id,
                criticidad=criticidad,
                canales=json.dumps(req.canales),
                webhook_url=req.webhook_url,
                slack_webhook_url=req.slack_webhook_url,
                escalation_contact=req.escalation_contact,
            )
            session.add(config)
        session.commit()
        return {
            "success": True,
            "config": {
                "tenant_id": tenant_id,
                "criticidad": criticidad,
                "canales": req.canales,
                "escalation_contact": req.escalation_contact,
            },
        }
