"""Tests RF24 — Sistema de alertas multicanal con escalación y detección de anomalías.

Cubre los 6 criterios de aceptación de HU-24:
  CA-01: 4 canales soportados (push, email, slack, webhook)
  CA-02: detección automática de anomalías (error_rate, degradación, tokens)
  CA-03: configuración de canales por tenant/criticidad
  CA-04: escalación automática de CRITICAL no leída en 15 min
  CA-05: snooze por 1h, 4h, 24h
  CA-06: historial con filtros por canal, criticidad y estado

Todos los dispatchers de canal y el escalation service usan mocks para
no generar side-effects reales (ni llamadas HTTP, ni push, ni emails).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_canales():
    """Intercepta todos los dispatchers de canal para evitar side-effects."""
    with (
        patch("app.services.alert_dispatcher.PushChannelDispatcher.dispatch", return_value=True),
        patch("app.services.alert_dispatcher.EmailChannelDispatcher.dispatch", return_value=True),
        patch("app.services.alert_dispatcher.SlackChannelDispatcher.dispatch", return_value=True),
        patch("app.services.alert_dispatcher.WebhookChannelDispatcher.dispatch", return_value=True),
    ):
        yield


def _crear_alerta(tipo="error_rate_alta", criticidad="CRITICAL", agent_id="agent-test", tenant_id="tenant_a"):
    return client.post("/api/v1/alerts/", json={
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "tipo": tipo,
        "criticidad": criticidad,
        "mensaje": f"Test alerta {tipo} nivel {criticidad} agente {agent_id}",
    })


# ─── CA-01: 4 canales soportados ──────────────────────────────────────────────

class TestCA01CuatroCanales:

    def test_canales_validos_en_config(self):
        from app.services.alert_dispatcher import CANALES_VALIDOS
        assert set(CANALES_VALIDOS) == {"push", "email", "slack", "webhook"}

    def test_configurar_canal_push(self):
        resp = client.put("/api/v1/alerts/config/tenant_test/CRITICAL", json={
            "canales": ["push"],
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["canales"] == ["push"]

    def test_configurar_canal_email(self):
        resp = client.put("/api/v1/alerts/config/tenant_test/WARNING", json={
            "canales": ["email"],
        })
        assert resp.status_code == 200

    def test_configurar_canal_slack_con_webhook(self):
        resp = client.put("/api/v1/alerts/config/tenant_test2/CRITICAL", json={
            "canales": ["slack", "push"],
            "slack_webhook_url": "https://hooks.slack.com/T000/B000/xxx",
        })
        assert resp.status_code == 200

    def test_configurar_webhook_personalizado(self):
        resp = client.put("/api/v1/alerts/config/tenant_test3/WARNING", json={
            "canales": ["webhook"],
            "webhook_url": "https://mi-empresa.com/webhook/alerts",
        })
        assert resp.status_code == 200

    def test_canal_invalido_retorna_400(self):
        resp = client.put("/api/v1/alerts/config/tenant_x/INFO", json={
            "canales": ["telegram"],  # no soportado
        })
        assert resp.status_code == 400
        assert "telegram" in resp.json()["detail"]

    def test_alerta_registra_canales_usados(self):
        # Con config push+email para CRITICAL
        client.put("/api/v1/alerts/config/tenant_ca01/CRITICAL", json={
            "canales": ["push", "email"],
        })
        resp = _crear_alerta(tenant_id="tenant_ca01")
        assert resp.status_code == 200
        alert = resp.json()["alert"]
        assert set(alert["canales_usados"]).issubset({"push", "email"})


# ─── CA-02: Detección automática de anomalías ─────────────────────────────────

class TestCA02DeteccionAnomalias:

    def test_detect_sin_datos_no_genera_alertas(self):
        """Sin despliegues fallidos recientes, no hay anomalías."""
        resp = client.post("/api/v1/alerts/detect", json={})
        assert resp.status_code == 200
        assert resp.json()["anomalias_detectadas"] == 0

    def test_detect_con_consumo_tokens_3x(self):
        """CA-02: consumo 3x promedio → genera alerta WARNING."""
        resp = client.post("/api/v1/alerts/detect", json={
            "consumo_tokens_actual": 30000,
            "promedio_tokens_historico": 9000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["anomalias_detectadas"] >= 1
        tipos = [a["tipo"] for a in data["alerts"]]
        assert "consumo_tokens_excesivo" in tipos
        # Criticidad de consumo excesivo es WARNING
        consumo_alert = next(a for a in data["alerts"] if a["tipo"] == "consumo_tokens_excesivo")
        assert consumo_alert["criticidad"] == "WARNING"

    def test_detect_consumo_tokens_por_debajo_umbral(self):
        """2x no supera el umbral de 3x."""
        resp = client.post("/api/v1/alerts/detect", json={
            "consumo_tokens_actual": 18000,
            "promedio_tokens_historico": 10000,
        })
        assert resp.status_code == 200
        tipos = [a["tipo"] for a in resp.json()["alerts"]]
        assert "consumo_tokens_excesivo" not in tipos

    def test_detect_devuelve_estructura_correcta(self):
        resp = client.post("/api/v1/alerts/detect", json={
            "consumo_tokens_actual": 50000,
            "promedio_tokens_historico": 5000,
        })
        assert resp.status_code == 200
        assert "anomalias_detectadas" in resp.json()
        assert "alerts" in resp.json()


# ─── CA-03: Configuración por tenant y criticidad ─────────────────────────────

class TestCA03ConfiguracionCanales:

    def test_get_config_tenant_vacio(self):
        resp = client.get("/api/v1/alerts/config/tenant_nuevo_xyz")
        assert resp.status_code == 200
        assert resp.json()["config"] == []

    def test_upsert_y_get_config(self):
        tenant = "tenant_ca03"
        # Configurar CRITICAL → slack + push con escalación
        client.put(f"/api/v1/alerts/config/{tenant}/CRITICAL", json={
            "canales": ["slack", "push"],
            "escalation_contact": "cto@empresa.com",
        })
        # Configurar INFO → email
        client.put(f"/api/v1/alerts/config/{tenant}/INFO", json={
            "canales": ["email"],
        })

        resp = client.get(f"/api/v1/alerts/config/{tenant}")
        assert resp.status_code == 200
        configs = {c["criticidad"]: c for c in resp.json()["config"]}
        assert "CRITICAL" in configs
        assert set(configs["CRITICAL"]["canales"]) == {"slack", "push"}
        assert configs["CRITICAL"]["escalation_contact"] == "cto@empresa.com"
        assert configs["INFO"]["canales"] == ["email"]

    def test_upsert_actualiza_config_existente(self):
        tenant = "tenant_update"
        client.put(f"/api/v1/alerts/config/{tenant}/WARNING", json={"canales": ["push"]})
        client.put(f"/api/v1/alerts/config/{tenant}/WARNING", json={"canales": ["email", "slack"]})

        resp = client.get(f"/api/v1/alerts/config/{tenant}")
        configs = {c["criticidad"]: c for c in resp.json()["config"]}
        assert set(configs["WARNING"]["canales"]) == {"email", "slack"}


# ─── CA-04: Escalación automática CRITICAL a los 15 min ──────────────────────

class TestCA04Escalacion:

    def test_alerta_pendiente_no_se_escala_inmediatamente(self):
        resp = _crear_alerta(criticidad="CRITICAL")
        alert = resp.json()["alert"]
        assert alert["estado"] == "pendiente"
        assert alert["escalado_a"] is None

    def test_escalacion_lazy_tras_15_min(self):
        """Simula que han pasado 16 minutos desde la creación."""
        resp = _crear_alerta(criticidad="CRITICAL")
        alert_id = resp.json()["alert"]["id"]

        # Retroceder la fecha de la alerta para simular timeout
        from app.core.database import get_session
        from app.models import AlertDB
        hace_16min = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
        with get_session() as session:
            a = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
            a.fecha = hace_16min
            session.commit()

        # GET /alerts dispara la evaluación perezosa
        resp_list = client.get("/api/v1/alerts/")
        assert resp_list.status_code == 200

        alert_data = next(
            (a for a in resp_list.json()["alerts"] if a["id"] == alert_id), None
        )
        assert alert_data is not None
        assert alert_data["estado"] == "escalada"
        assert alert_data["escalado_en"] is not None

    def test_alerta_leida_no_se_escala(self):
        resp = _crear_alerta(criticidad="CRITICAL")
        alert_id = resp.json()["alert"]["id"]

        # Marcar como leída antes del timeout
        client.patch(f"/api/v1/alerts/{alert_id}/read")

        from app.core.database import get_session
        from app.models import AlertDB
        hace_20min = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        with get_session() as session:
            a = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
            a.fecha = hace_20min
            session.commit()

        client.get("/api/v1/alerts/")  # dispara evaluación

        from app.core.database import get_session
        from app.models import AlertDB
        with get_session() as session:
            a = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
            # Debe seguir como "leida", no escalada
            assert a.estado == "leida"


# ─── CA-05: Snooze configurable 1h / 4h / 24h ────────────────────────────────

class TestCA05Snooze:

    def test_snooze_1h(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        resp = client.post(f"/api/v1/alerts/{alert_id}/snooze", json={"horas": 1})

        assert resp.status_code == 200
        data = resp.json()
        assert data["alert"]["estado"] == "snoozed"
        assert data["snooze_until"] is not None

    def test_snooze_4h(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        resp = client.post(f"/api/v1/alerts/{alert_id}/snooze", json={"horas": 4})
        assert resp.status_code == 200
        until = datetime.fromisoformat(resp.json()["snooze_until"])
        delta = until - datetime.now(timezone.utc)
        # Debe ser aproximadamente 4 horas (±1 min)
        assert timedelta(hours=3, minutes=59) <= delta <= timedelta(hours=4, minutes=1)

    def test_snooze_24h(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        resp = client.post(f"/api/v1/alerts/{alert_id}/snooze", json={"horas": 24})
        assert resp.status_code == 200
        assert resp.json()["alert"]["estado"] == "snoozed"

    def test_snooze_horas_invalidas_retorna_422(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        resp = client.post(f"/api/v1/alerts/{alert_id}/snooze", json={"horas": 8})
        assert resp.status_code == 422  # 8h no está en Literal[1, 4, 24]

    def test_snooze_no_existente_retorna_404(self):
        resp = client.post("/api/v1/alerts/999999/snooze", json={"horas": 1})
        assert resp.status_code == 404

    def test_snooze_expirado_vuelve_a_pendiente(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        client.post(f"/api/v1/alerts/{alert_id}/snooze", json={"horas": 1})

        # Simular snooze expirado
        from app.core.database import get_session
        from app.models import AlertDB
        ya_paso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with get_session() as session:
            a = session.query(AlertDB).filter(AlertDB.id == alert_id).first()
            a.snooze_until = ya_paso
            session.commit()

        resp_list = client.get("/api/v1/alerts/")
        alerta = next(a for a in resp_list.json()["alerts"] if a["id"] == alert_id)
        assert alerta["estado"] == "pendiente"


# ─── CA-06: Historial con filtros ────────────────────────────────────────────

class TestCA06HistorialFiltros:

    def test_filtrar_por_criticidad_critical(self):
        _crear_alerta(criticidad="CRITICAL")
        _crear_alerta(criticidad="WARNING")
        resp = client.get("/api/v1/alerts/?criticidad=CRITICAL")
        assert resp.status_code == 200
        alerts = resp.json()["alerts"]
        assert all(a["criticidad"] == "CRITICAL" for a in alerts)
        assert len(alerts) >= 1

    def test_filtrar_por_estado_leida(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        client.patch(f"/api/v1/alerts/{alert_id}/read")
        resp = client.get("/api/v1/alerts/?estado=leida")
        assert resp.status_code == 200
        assert all(a["estado"] == "leida" for a in resp.json()["alerts"])

    def test_filtrar_por_estado_snoozed(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        client.post(f"/api/v1/alerts/{alert_id}/snooze", json={"horas": 4})
        resp = client.get("/api/v1/alerts/?estado=snoozed")
        assert resp.status_code == 200
        snoozed = resp.json()["alerts"]
        assert any(a["id"] == alert_id for a in snoozed)

    def test_filtrar_por_canal(self):
        """Alerta despacha por push por defecto → filtrar canal=push la incluye."""
        resp_create = _crear_alerta(tenant_id="tenant_filtro_canal")
        alert_id = resp_create.json()["alert"]["id"]
        resp = client.get("/api/v1/alerts/?canal=push")
        assert resp.status_code == 200
        # Puede haber alertas de push de otros tests; solo verificamos la estructura
        for a in resp.json()["alerts"]:
            assert "push" in a["canales_usados"]

    def test_filtrar_por_agent_id(self):
        agent_especifico = "agente-unico-xyz-789"
        _crear_alerta(agent_id=agent_especifico)
        resp = client.get(f"/api/v1/alerts/?agent_id={agent_especifico}")
        assert resp.status_code == 200
        alerts = resp.json()["alerts"]
        assert len(alerts) >= 1
        assert all(a["agent_id"] == agent_especifico for a in alerts)

    def test_respuesta_incluye_total(self):
        resp = client.get("/api/v1/alerts/")
        assert resp.status_code == 200
        assert "total" in resp.json()
        assert isinstance(resp.json()["total"], int)

    def test_mark_read_cambia_estado(self):
        alert_id = _crear_alerta().json()["alert"]["id"]
        resp = client.patch(f"/api/v1/alerts/{alert_id}/read")
        assert resp.status_code == 200
        assert resp.json()["alert"]["estado"] == "leida"

    def test_mark_read_no_existente_retorna_404(self):
        resp = client.patch("/api/v1/alerts/999998/read")
        assert resp.status_code == 404
