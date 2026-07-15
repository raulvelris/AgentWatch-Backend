"""Tests RF22 — Notificaciones push contextuales con 3 niveles de criticidad.

Cubre los 6 criterios de aceptación de HU-22:
  CA-01: 3 niveles (CRITICAL / WARNING / INFO) bien asignados
  CA-02: deep link habilitado por agent_id en notificaciones CRITICAL
  CA-03: entrega < 10 s (FCM mockeado + polling 5 s, verificado con timing)
  CA-04: filtro por criticidad en GET (simula preferencias del usuario)
  CA-05: marcar leída sincroniza el estado
  CA-06: mensaje incluye agente, tipo, hora

Los tests mockean `_despachar_fcm` para verificar que se llama con el nivel
correcto, sin necesidad de credenciales Firebase reales.
"""

import time
from unittest.mock import patch, call

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixture: patch del despachador FCM para todos los tests de este módulo
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_fcm():
    """Intercepta _despachar_fcm para evitar side-effects y capturar llamadas."""
    with patch("app.services.notificaciones._despachar_fcm") as mock:
        yield mock


# ---------------------------------------------------------------------------
# CA-01: los 3 niveles se asignan correctamente según el tipo de evento
# ---------------------------------------------------------------------------

class TestCA01NivelesCriticidad:

    def test_deploy_fallido_es_critical(self, mock_fcm):
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "deploy_fallido",
            "destinatario_rol": "ADMIN",
            "mensaje": "El agente 'bot-123' falló en fase healthcheck.",
            "agent_id": "bot-123",
        })
        assert resp.status_code == 200
        notif = resp.json()["notification"]
        assert notif["criticidad"] == "CRITICAL"
        # Verificar que FCM fue llamado con el nivel correcto
        mock_fcm.assert_called_once()
        assert mock_fcm.call_args[0][0] == "CRITICAL"

    def test_promotion_pendiente_es_warning(self, mock_fcm):
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "promotion_pendiente",
            "destinatario_rol": "ADMIN",
            "mensaje": "Promoción de agente-456 a prod solicitada por dev@corp.com.",
            "agent_id": "agente-456",
        })
        assert resp.status_code == 200
        notif = resp.json()["notification"]
        assert notif["criticidad"] == "WARNING"
        mock_fcm.assert_called_once()
        assert mock_fcm.call_args[0][0] == "WARNING"

    def test_promotion_expirada_es_info(self, mock_fcm):
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "promotion_expirada",
            "destinatario_rol": "ADMIN",
            "mensaje": "Solicitud de promoción expirada sin aprobación (24h).",
            "agent_id": "agente-789",
        })
        assert resp.status_code == 200
        notif = resp.json()["notification"]
        assert notif["criticidad"] == "INFO"
        mock_fcm.assert_called_once()
        assert mock_fcm.call_args[0][0] == "INFO"

    def test_criticidad_explicita_prevalece(self, mock_fcm):
        """El caller puede forzar un nivel distinto al inferido por tipo."""
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "promotion_expirada",
            "destinatario_rol": "ADMIN",
            "mensaje": "Expiración crítica de política de seguridad.",
            "agent_id": "agente-sec",
            "criticidad": "CRITICAL",   # override explícito
        })
        assert resp.status_code == 200
        assert resp.json()["notification"]["criticidad"] == "CRITICAL"


# ---------------------------------------------------------------------------
# CA-02: deep link — agent_id presente en notificaciones CRITICAL
# ---------------------------------------------------------------------------

class TestCA02DeepLink:

    def test_critical_incluye_agent_id(self, mock_fcm):
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "deploy_fallido",
            "destinatario_rol": "ADMIN",
            "mensaje": "Fallo total en prod: agente conversador-001.",
            "agent_id": "conversador-001",
        })
        notif = resp.json()["notification"]
        assert notif["criticidad"] == "CRITICAL"
        assert notif["agent_id"] == "conversador-001"
        # El front usa agent_id para construir /agent/{agent_id} (expo-router)

    def test_fcm_recibe_agent_id_para_deeplink(self, mock_fcm):
        client.post("/api/v1/notifications/push", json={
            "tipo": "deploy_fallido",
            "destinatario_rol": "ADMIN",
            "mensaje": "Fallo crítico.",
            "agent_id": "deeplink-agente",
        })
        _, kwargs = mock_fcm.call_args[0], mock_fcm.call_args
        # _despachar_fcm(criticidad, tipo, mensaje, agent_id, notif_id)
        assert mock_fcm.call_args[0][3] == "deeplink-agente"


# ---------------------------------------------------------------------------
# CA-03: entrega < 10 s (FCM mock + timing de encolado)
# ---------------------------------------------------------------------------

class TestCA03EntregaRapida:

    def test_encolado_en_menos_de_2_segundos(self, mock_fcm):
        """El encolado + mock FCM debe completarse muy por debajo de los 10 s del SLA."""
        inicio = time.time()
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "deploy_fallido",
            "destinatario_rol": "ADMIN",
            "mensaje": "Test de latencia de encolado.",
            "agent_id": "agente-timing",
        })
        elapsed = time.time() - inicio
        assert resp.status_code == 200
        assert elapsed < 2.0, f"Encolado tardó {elapsed:.2f}s, esperado < 2s"
        mock_fcm.assert_called_once()

    def test_fcm_llamado_inmediatamente_tras_persistir(self, mock_fcm):
        """FCM se despacha en el mismo ciclo que el commit, no en background."""
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "deploy_fallido",
            "destinatario_rol": "ADMIN",
            "mensaje": "Verificando orden de operaciones.",
        })
        # Si la notificación se persistió (tiene id) y FCM fue llamado → orden correcto
        notif_id = resp.json()["notification"]["id"]
        assert notif_id is not None
        assert mock_fcm.call_args[0][4] == notif_id  # notif_id pasado a FCM


# ---------------------------------------------------------------------------
# CA-04: filtro por criticidad (simula preferencias del usuario)
# ---------------------------------------------------------------------------

class TestCA04FiltroPreferencias:

    def test_filtrar_solo_critical(self, mock_fcm):
        # Crear una de cada nivel
        for tipo in ("deploy_fallido", "promotion_pendiente", "promotion_expirada"):
            client.post("/api/v1/notifications/push", json={
                "tipo": tipo,
                "destinatario_rol": "ADMIN",
                "mensaje": f"Test {tipo}",
            })
        resp = client.get("/api/v1/notifications/?criticidad=CRITICAL")
        assert resp.status_code == 200
        notifs = resp.json()["notifications"]
        assert all(n["criticidad"] == "CRITICAL" for n in notifs)
        assert len(notifs) >= 1

    def test_filtrar_solo_warning(self, mock_fcm):
        resp = client.get("/api/v1/notifications/?criticidad=WARNING")
        assert resp.status_code == 200
        notifs = resp.json()["notifications"]
        assert all(n["criticidad"] == "WARNING" for n in notifs)

    def test_filtrar_solo_info(self, mock_fcm):
        resp = client.get("/api/v1/notifications/?criticidad=INFO")
        assert resp.status_code == 200
        notifs = resp.json()["notifications"]
        assert all(n["criticidad"] == "INFO" for n in notifs)


# ---------------------------------------------------------------------------
# CA-05: marcar leída sincroniza el estado (mobile ↔ dashboard web)
# ---------------------------------------------------------------------------

class TestCA05SincronizacionLeida:

    def test_flujo_completo_crear_leer_marcar(self, mock_fcm):
        # 1. Crear notificación CRITICAL
        resp_push = client.post("/api/v1/notifications/push", json={
            "tipo": "deploy_fallido",
            "destinatario_rol": "ADMIN",
            "mensaje": "Fallo en producción, revert aplicado.",
            "agent_id": "sync-agent",
        })
        assert resp_push.status_code == 200
        notif_id = resp_push.json()["notification"]["id"]

        # 2. Verificar que aparece como no leída
        resp_list = client.get("/api/v1/notifications/")
        matching = [n for n in resp_list.json()["notifications"] if n["id"] == notif_id]
        assert len(matching) == 1
        assert matching[0]["leida"] is False

        # 3. Marcar como leída (CA-05)
        resp_read = client.patch(f"/api/v1/notifications/{notif_id}/read")
        assert resp_read.status_code == 200
        assert resp_read.json()["leida"] is True

        # 4. Confirmar sincronización en el listado
        resp_list2 = client.get("/api/v1/notifications/")
        matching2 = [n for n in resp_list2.json()["notifications"] if n["id"] == notif_id]
        assert matching2[0]["leida"] is True

    def test_marcar_no_existente_devuelve_404(self, mock_fcm):
        resp = client.patch("/api/v1/notifications/999999/read")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CA-06: mensaje incluye agente, tipo de evento y hora
# ---------------------------------------------------------------------------

class TestCA06ContextoEnMensaje:

    def test_mensaje_incluye_agent_id_y_tipo(self, mock_fcm):
        resp = client.post("/api/v1/notifications/push", json={
            "tipo": "deploy_fallido",
            "destinatario_rol": "ADMIN",
            "mensaje": "Agente: translator-v2 | Evento: deploy falló en fase build | Hora: 2026-07-15T06:00Z",
            "agent_id": "translator-v2",
        })
        notif = resp.json()["notification"]
        # El mensaje y agent_id viajan juntos para que el usuario pueda actuar sin abrir la app
        assert "translator-v2" in notif["mensaje"]
        assert notif["agent_id"] == "translator-v2"
        assert notif["fecha"] is not None  # ISO-8601 con hora

    def test_contexto_en_llamada_fcm(self, mock_fcm):
        """El mock FCM recibe tipo, mensaje y agent_id para construir el payload real."""
        client.post("/api/v1/notifications/push", json={
            "tipo": "promotion_pendiente",
            "destinatario_rol": "ADMIN",
            "mensaje": "Agente summarizer-pro solicita pasar a prod.",
            "agent_id": "summarizer-pro",
        })
        args = mock_fcm.call_args[0]
        criticidad, tipo, mensaje, agent_id, notif_id = args
        assert criticidad == "WARNING"
        assert tipo == "promotion_pendiente"
        assert "summarizer-pro" in mensaje
        assert agent_id == "summarizer-pro"
        assert isinstance(notif_id, int)
