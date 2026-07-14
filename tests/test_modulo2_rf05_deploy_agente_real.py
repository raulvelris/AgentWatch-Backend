"""RF05/RF07 tras la integración de AgentDB (commit b4a3188): el deploy usa
la configuración REAL persistida del agente, y la siembra de los agentes demo
corre después de init_db() (con la BD fresca de la suite tienen que estar).
"""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.routers.versions import _hash_config
from tests.util_agentes import crear_agente

client = TestClient(app)

DEMO_SOPORTE = "12345678-1234-5678-1234-567812345678"
DEMO_ANALISTA = "87654321-4321-8765-4321-876543210987"


def _h(usuario: str = "admin_a") -> dict:
    token = client.get("/api/v1/auth/login", params={"usuario": usuario}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_agentes_demo_sembrados_tras_arranque():
    # Regresión del arranque: la siembra corre DESPUÉS de init_db(). Antes,
    # la llamada a nivel de import moría con "no such table: agents" y ni el
    # server ni la suite podían arrancar con una BD fresca.
    r = client.get("/api/v1/agents/")
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()["agents"]}
    assert {DEMO_SOPORTE, DEMO_ANALISTA} <= ids


def test_deploy_agente_inexistente_da_404_json():
    # Antes del fix, el 404 se levantaba ADENTRO del generador SSE con los
    # headers 200 ya enviados: stream roto sin frame done/error. Ahora el
    # chequeo corre en el handler y el cliente recibe un 404 JSON limpio.
    fantasma = str(uuid.uuid4())
    r = client.post(f"/api/v1/agents/{fantasma}/deploy", headers=_h())
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "configuración" in r.json()["detail"]
    # Sin efectos colaterales: ni versión candidata ni registro de despliegue.
    assert client.get(f"/api/v1/agents/{fantasma}/versions").json()["versions"] == []
    assert (
        client.get(f"/api/v1/agents/{fantasma}/deployments").json()["deployments"] == []
    )


def test_fallo_invalido_gana_al_agente_inexistente():
    # Pin del orden de chequeos: la validación de ?fallo (400) corre antes que
    # la existencia del agente (404). test_deploy_fallo_en_fase_invalida_da_400
    # (agente inexistente + fase inválida) depende de este orden.
    fantasma = str(uuid.uuid4())
    r = client.post(f"/api/v1/agents/{fantasma}/deploy?fallo=meteorito", headers=_h())
    assert r.status_code == 400


def test_deploy_agente_demo_funciona():
    # Los agentes demo sembrados son deployables tal cual (config en AgentDB).
    r = client.post(f"/api/v1/agents/{DEMO_SOPORTE}/deploy", headers=_h())
    assert r.status_code == 200
    assert '"estado": "success"' in r.text


def test_hash_de_version_es_el_de_la_config_real():
    # RF07: el hash de la versión sale de la config real persistida (AgentDB),
    # con el mismo dump canónico, y NO del fallback {"agent_id": ...}.
    agente = crear_agente(client)
    cfg = client.get(f"/api/v1/agents/{agente}").json()["agent"]

    r = client.post(f"/api/v1/agents/{agente}/deploy", headers=_h())
    assert r.status_code == 200

    v1 = client.get(f"/api/v1/agents/{agente}/versions").json()["versions"][0]
    assert v1["hash_sha256"] == _hash_config(cfg)
    assert v1["hash_sha256"] != _hash_config({"agent_id": agente})

    # Config distinta (cambia el estado) => hash distinto en el próximo deploy.
    rp = client.patch(f"/api/v1/agents/{agente}/state", json={"estado": "PAUSED"})
    assert rp.status_code == 200
    client.post(f"/api/v1/agents/{agente}/deploy", headers=_h())
    versiones = client.get(f"/api/v1/agents/{agente}/versions").json()["versions"]
    assert versiones[1]["hash_sha256"] != v1["hash_sha256"]
