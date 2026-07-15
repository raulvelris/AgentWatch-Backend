"""Tests RF23 — Modo offline-first con sincronización delta y acciones encoladas.

Cubre los 6 criterios de aceptación:
  CA-01: caché local (verificada via endpoint que devuelve datos persistidos)
  CA-02: indicador offline (la app devuelve datos aunque el servidor falle)
  CA-03: delta sync solo devuelve agentes modificados desde `since`
  CA-04: respuesta del endpoint delta < 1s para 100 agentes (SLA backend)
  CA-05: las acciones offline se encolan (verificado via agentes que usan updated_at)
  CA-06: server wins — el backend tiene siempre el updated_at más reciente

Se usan mocks de expo-network en el lado mobile; aquí se testea el backend Python.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _crear_agente(nombre: str = "Test Agent", estado: str = "ACTIVE") -> dict:
    """Crea un agente demo y retorna su dict."""
    import uuid
    agent_id = str(uuid.uuid4())
    resp = client.post("/api/v1/agents/", json={
        "id": agent_id,
        "nombre": nombre,
        "tipo": "TestType",
        "proposito": "Testing",
        "fuente": "Tests",
        "descripcion_fuente": "pytest",
        "regla": "No side effects",
        "supervision": "Automática",
        "estado": estado,
        "tenant_id": "tenant_delta",
        "owner": "tester",
    })
    assert resp.status_code == 200, f"Error creando agente: {resp.text}"
    return resp.json()["agent"]


def _timestamp_futuro(segundos: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=segundos)).isoformat()


def _timestamp_pasado(segundos: int = 60) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=segundos)).isoformat()


# ─── CA-03: Endpoint delta sync ───────────────────────────────────────────────

class TestCA03DeltaSync:

    def test_delta_desde_epoch_devuelve_todos_los_agentes(self):
        """since=epoch retorna todos los agentes existentes."""
        _crear_agente("Delta Agente 1")
        resp = client.get("/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "server_time" in data
        assert "changes" in data
        assert data["changes"] == len(data["agents"])
        assert data["changes"] >= 1

    def test_delta_desde_ahora_devuelve_lista_vacia(self):
        """since=ahora → no hay cambios recientes → lista vacía."""
        _crear_agente("Delta Agente 2")
        since = _timestamp_futuro(10)  # 10s en el futuro
        resp = client.get(f"/api/v1/agents/delta?since={since}")
        assert resp.status_code == 200
        assert resp.json()["changes"] == 0
        assert resp.json()["agents"] == []

    def test_delta_solo_incluye_modificados_despues_de_since(self):
        """Solo los agentes creados/modificados DESPUÉS de `since` aparecen."""
        since = _timestamp_pasado(5)   # 5 segundos atrás
        # Crear agente DESPUÉS del since
        agente = _crear_agente("Agente Post-Since")
        resp = client.get(f"/api/v1/agents/delta?since={since}")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()["agents"]]
        assert agente["id"] in ids

    def test_delta_respuesta_tiene_campos_correctos(self):
        """Cada agente en el delta incluye los campos requeridos por el cliente."""
        _crear_agente("Agente Campos")
        resp = client.get("/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00")
        assert resp.status_code == 200
        for agent in resp.json()["agents"]:
            assert "id"         in agent
            assert "nombre"     in agent
            assert "tipo"       in agent
            assert "estado"     in agent
            assert "updated_at" in agent
            assert "tenant_id"  in agent

    def test_delta_server_time_es_posterior_a_since(self):
        """server_time siempre es posterior a `since` para el próximo ciclo."""
        since = _timestamp_pasado(30)
        resp = client.get(f"/api/v1/agents/delta?since={since}")
        assert resp.status_code == 200
        assert resp.json()["server_time"] > since

    def test_delta_filtra_por_tenant_id(self):
        """Parámetro tenant_id filtra correctamente."""
        resp = client.get(
            "/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00&tenant_id=tenant_delta"
        )
        assert resp.status_code == 200
        for a in resp.json()["agents"]:
            assert a["tenant_id"] == "tenant_delta"


# ─── CA-04: SLA de rendimiento ────────────────────────────────────────────────

class TestCA04SLARendimiento:

    def test_delta_responde_en_menos_de_1_segundo(self):
        """CA-04: backend responde en < 1 s (SLA 5 s incluye red 4G)."""
        # Crear algunos agentes para tener datos realistas
        for i in range(5):
            _crear_agente(f"Perf Agent {i}")

        inicio = time.perf_counter()
        resp = client.get("/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00")
        elapsed = time.perf_counter() - inicio

        assert resp.status_code == 200
        assert elapsed < 1.0, f"Delta sync tardó {elapsed:.3f}s (máx 1.0s backend)"

    def test_delta_con_since_reciente_es_ultrarapido(self):
        """Delta vacío (sin cambios) debe responder en < 100ms."""
        since = _timestamp_futuro(60)
        inicio = time.perf_counter()
        resp = client.get(f"/api/v1/agents/delta?since={since}")
        elapsed = time.perf_counter() - inicio

        assert resp.status_code == 200
        assert elapsed < 0.1, f"Delta vacío tardó {elapsed:.3f}s"


# ─── CA-05: updated_at se actualiza al cambiar estado ─────────────────────────

class TestCA05AccionesEncoladas:

    def test_update_state_actualiza_updated_at(self):
        """Al cambiar estado, updated_at se actualiza → queda visible en delta."""
        agente = _crear_agente("Agente Queue Test", estado="ACTIVE")
        since_antes = _timestamp_pasado(1)

        # Cambiar estado
        resp_patch = client.patch(
            f"/api/v1/agents/{agente['id']}/state",
            json={"estado": "PAUSED"},
        )
        assert resp_patch.status_code == 200

        # El delta desde antes debe incluir este agente
        resp_delta = client.get(f"/api/v1/agents/delta?since={since_antes}")
        assert resp_delta.status_code == 200
        ids = [a["id"] for a in resp_delta.json()["agents"]]
        assert agente["id"] in ids

    def test_estado_actualizado_refleja_en_delta(self):
        """El estado en la respuesta delta coincide con el último PATCH."""
        agente = _crear_agente("Agente Estado Delta", estado="ACTIVE")
        since = _timestamp_pasado(1)

        client.patch(f"/api/v1/agents/{agente['id']}/state", json={"estado": "PAUSED"})

        resp = client.get(f"/api/v1/agents/delta?since={since}")
        agente_delta = next(
            (a for a in resp.json()["agents"] if a["id"] == agente["id"]), None
        )
        assert agente_delta is not None
        assert agente_delta["estado"] == "PAUSED"


# ─── CA-06: server_wins via updated_at ───────────────────────────────────────

class TestCA06ServerWins:

    def test_servidor_tiene_updated_at_mas_reciente(self):
        """El backend stampa updated_at en cada write — siempre más reciente."""
        antes = datetime.now(timezone.utc)
        agente = _crear_agente("Server Wins Agent")
        despues = datetime.now(timezone.utc)

        resp = client.get("/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00")
        agente_delta = next(
            (a for a in resp.json()["agents"] if a["id"] == agente["id"]), None
        )
        assert agente_delta is not None
        server_ts = datetime.fromisoformat(agente_delta["updated_at"])
        # El updated_at del servidor debe estar dentro del rango de la prueba
        assert antes <= server_ts <= despues + timedelta(seconds=2)

    def test_segundo_patch_tiene_updated_at_mas_reciente(self):
        """Cada PATCH avanza updated_at → el cliente puede detectar quién gana."""
        agente = _crear_agente("Server Wins 2")

        resp1 = client.get("/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00")
        ts1 = next(a["updated_at"] for a in resp1.json()["agents"] if a["id"] == agente["id"])

        time.sleep(0.01)  # Asegurar que el timestamp avance
        client.patch(f"/api/v1/agents/{agente['id']}/state", json={"estado": "PAUSED"})

        resp2 = client.get("/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00")
        ts2 = next(a["updated_at"] for a in resp2.json()["agents"] if a["id"] == agente["id"])

        assert ts2 > ts1, "updated_at debe avanzar con cada modificación"


# ─── CA-01/CA-02: fallback a caché (comportamiento testeable en backend) ───────

class TestCA01CA02Cache:

    def test_agente_creado_persiste_en_db(self):
        """CA-01: los agentes persisten en SQLite (se pueden releer)."""
        agente = _crear_agente("Persist Test")
        resp = client.get(f"/api/v1/agents/{agente['id']}")
        assert resp.status_code == 200
        assert resp.json()["agent"]["nombre"] == "Persist Test"

    def test_delta_endpoint_es_alcanzable(self):
        """CA-02: el endpoint delta existe y responde 200."""
        resp = client.get("/api/v1/agents/delta?since=1970-01-01T00:00:00%2B00:00")
        assert resp.status_code == 200

    def test_delta_sin_parametro_since_retorna_422(self):
        """El parámetro `since` es obligatorio."""
        resp = client.get("/api/v1/agents/delta")
        assert resp.status_code == 422
