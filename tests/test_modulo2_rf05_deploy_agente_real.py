"""RF05/RF07 tras la integración de AgentDB (commit b4a3188): el deploy usa
la configuración REAL persistida del agente, y la siembra de los agentes demo
corre después de init_db() (con la BD fresca de la suite tienen que estar).
"""

from fastapi.testclient import TestClient

from app.main import app

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
