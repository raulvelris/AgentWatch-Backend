"""AnomalyDetector — RF24 CA-02: detección automática de anomalías.

Reglas implementadas (sin Prometheus; usa datos de la BD local):
  1. error_rate_alta     : tasa de fallos > 5% en los últimos 10 despliegues
  2. degradacion_calidad : proporción de fallos en ventana reciente > 20%
  3. consumo_tokens      : placeholder — 3x sobre promedio histórico
                           (en producción: consulta a Prometheus/Grafana)

En producción, cada `_detectar_*` haría:
    metrics = httpx.get(PROMETHEUS_URL, params={"query": "<promql>"}).json()
    value = float(metrics["data"]["result"][0]["value"][1])

Para el prototipo académico las métricas se calculan sobre DeploymentRecordDB.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.database import get_session
from app.models import DeploymentRecordDB

logger = logging.getLogger(__name__)

# ─── Umbrales CA-02 ───────────────────────────────────────────────────────────
ERROR_RATE_THRESHOLD = 0.05        # > 5 %
DEGRADACION_THRESHOLD = 0.20       # > 20 %
TOKEN_CONSUMO_FACTOR = 3.0         # 3x promedio histórico
VENTANA_MINUTOS = 10               # últimos 10 minutos
VENTANA_DESPLIEGUES = 10           # últimos N despliegues para tasa


@dataclass
class Anomalia:
    tipo: str           # identificador interno
    criticidad: str     # "CRITICAL" | "WARNING" | "INFO"
    mensaje: str        # texto para el usuario (CA-06 del RF22)
    agent_id: str | None = None
    metrica_valor: float | None = None


def _tasa_error_ultimos_n(agent_id: str | None, n: int) -> float:
    """Calcula tasa de fallos en los últimos N despliegues del agente (o global)."""
    with get_session() as session:
        q = session.query(DeploymentRecordDB)
        if agent_id:
            q = q.filter(DeploymentRecordDB.agent_id == agent_id)
        registros = q.order_by(DeploymentRecordDB.id.desc()).limit(n).all()

    if not registros:
        return 0.0
    fallidos = sum(1 for r in registros if r.resultado == "failed")
    return fallidos / len(registros)


def _tasa_error_ventana_tiempo(agent_id: str | None, minutos: int) -> float:
    """Calcula tasa de fallos en los últimos `minutos` minutos."""
    limite = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    with get_session() as session:
        q = session.query(DeploymentRecordDB).filter(
            DeploymentRecordDB.fecha >= limite.isoformat()
        )
        if agent_id:
            q = q.filter(DeploymentRecordDB.agent_id == agent_id)
        registros = q.all()

    if not registros:
        return 0.0
    fallidos = sum(1 for r in registros if r.resultado == "failed")
    return fallidos / len(registros)


# ─── Detectores individuales ─────────────────────────────────────────────────

def _detectar_error_rate(agent_id: str | None) -> Anomalia | None:
    """CA-02: error rate > 5% en los últimos 10 minutos."""
    tasa = _tasa_error_ventana_tiempo(agent_id, VENTANA_MINUTOS)
    if tasa > ERROR_RATE_THRESHOLD:
        return Anomalia(
            tipo="error_rate_alta",
            criticidad="CRITICAL",
            mensaje=(
                f"Tasa de error crítica: {tasa:.1%} de fallos en los últimos "
                f"{VENTANA_MINUTOS} min"
                + (f" (agente: {agent_id})" if agent_id else " (global)")
                + f". Umbral: {ERROR_RATE_THRESHOLD:.0%}."
            ),
            agent_id=agent_id,
            metrica_valor=tasa,
        )
    return None


def _detectar_degradacion_calidad(agent_id: str | None) -> Anomalia | None:
    """CA-02: degradación de calidad > 20% en últimos N despliegues."""
    tasa = _tasa_error_ultimos_n(agent_id, VENTANA_DESPLIEGUES)
    if tasa > DEGRADACION_THRESHOLD:
        return Anomalia(
            tipo="degradacion_calidad",
            criticidad="WARNING",
            mensaje=(
                f"Degradación de calidad: {tasa:.1%} de los últimos "
                f"{VENTANA_DESPLIEGUES} despliegues fallaron"
                + (f" (agente: {agent_id})" if agent_id else " (global)")
                + f". Umbral: {DEGRADACION_THRESHOLD:.0%}."
            ),
            agent_id=agent_id,
            metrica_valor=tasa,
        )
    return None


def _detectar_consumo_tokens(
    agent_id: str | None,
    consumo_actual: float | None = None,
    promedio_historico: float | None = None,
) -> Anomalia | None:
    """CA-02: consumo de tokens 3x sobre el promedio histórico.

    En el prototipo académico requiere que el caller pase los valores
    (vendrían de Prometheus / métricas del módulo 5).  Si no se pasan,
    la detección se omite sin levantar error.
    """
    if consumo_actual is None or promedio_historico is None or promedio_historico == 0:
        return None
    ratio = consumo_actual / promedio_historico
    if ratio >= TOKEN_CONSUMO_FACTOR:
        return Anomalia(
            tipo="consumo_tokens_excesivo",
            criticidad="WARNING",
            mensaje=(
                f"Consumo de tokens {ratio:.1f}x sobre el promedio histórico "
                + (f"(agente: {agent_id})" if agent_id else "(global)")
                + f". Actual: {consumo_actual:,.0f} | Promedio: {promedio_historico:,.0f}."
            ),
            agent_id=agent_id,
            metrica_valor=ratio,
        )
    return None


# ─── Detector principal ───────────────────────────────────────────────────────

def detectar_anomalias(
    agent_id: str | None = None,
    consumo_tokens_actual: float | None = None,
    promedio_tokens_historico: float | None = None,
) -> list[Anomalia]:
    """Ejecuta todas las reglas de detección. Retorna lista de anomalías encontradas.

    Parámetros opcionales `consumo_tokens_*` permiten pasar métricas externas
    (ej. del módulo 5 de trazabilidad) para la regla de consumo de tokens.
    """
    detectores = [
        lambda: _detectar_error_rate(agent_id),
        lambda: _detectar_degradacion_calidad(agent_id),
        lambda: _detectar_consumo_tokens(
            agent_id, consumo_tokens_actual, promedio_tokens_historico
        ),
    ]

    anomalias = []
    for detector in detectores:
        try:
            resultado = detector()
            if resultado:
                anomalias.append(resultado)
                logger.info(
                    "[AnomalyDetector] Anomalía detectada: tipo=%s criticidad=%s valor=%s",
                    resultado.tipo, resultado.criticidad, resultado.metrica_valor,
                )
        except Exception as exc:
            logger.error("[AnomalyDetector] Error en detector: %s", exc)

    return anomalias
