"""RF07: la versión que genera un rollback representa a la versión objetivo.

Antes del fix, rollback llamaba registrar_version sin configuración y el
hash_sha256 de la versión nueva era el del fallback {"agent_id": ...}: un
placeholder constante por agente, no el hash de la versión a la que se
vuelve. Ahora hereda el hash del objetivo (hash_explicito).
"""

from fastapi.testclient import TestClient

from app.main import app
from app.routers.versions import _hash_config, registrar_version
from tests.util_agentes import crear_agente

client = TestClient(app)


def _h(usuario: str = "admin_a") -> dict:
    token = client.get("/api/v1/auth/login", params={"usuario": usuario}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _preparar_dos_versiones_con_hash_distinto() -> tuple[str, dict, dict]:
    """v1 con estado ACTIVE y v2 con estado PAUSED: hashes distintos seguro."""
    agente = crear_agente(client)
    client.post(f"/api/v1/agents/{agente}/deploy", headers=_h())
    client.patch(f"/api/v1/agents/{agente}/state", json={"estado": "PAUSED"})
    client.post(f"/api/v1/agents/{agente}/deploy", headers=_h())
    v1, v2 = client.get(f"/api/v1/agents/{agente}/versions").json()["versions"]
    assert v1["hash_sha256"] != v2["hash_sha256"]
    return agente, v1, v2


def test_rollback_hereda_hash_de_version_objetivo(sin_sleep):
    agente, v1, v2 = _preparar_dos_versiones_con_hash_distinto()
    r = client.post(f"/api/v1/agents/{agente}/rollback/{v1['id']}", headers=_h())
    assert r.status_code == 200
    v3 = r.json()["version"]
    assert v3["estado"] == "rollback"
    # Doble verificación: en la respuesta Y releyendo el historial de la BD.
    assert v3["hash_sha256"] == v1["hash_sha256"]
    historial = client.get(f"/api/v1/agents/{agente}/versions").json()["versions"]
    assert historial[-1]["hash_sha256"] == v1["hash_sha256"]
    assert historial[-1]["hash_sha256"] != v2["hash_sha256"]
    # La versión objetivo no se modificó (append-only, RF07).
    assert historial[0]["hash_sha256"] == v1["hash_sha256"]


def test_rollback_encadenado_conserva_hash(sin_sleep):
    # Rollback de un rollback: el hash original sigue viajando intacto.
    agente, v1, _v2 = _preparar_dos_versiones_con_hash_distinto()
    v3 = client.post(
        f"/api/v1/agents/{agente}/rollback/{v1['id']}", headers=_h()
    ).json()["version"]
    r = client.post(f"/api/v1/agents/{agente}/rollback/{v3['id']}", headers=_h())
    assert r.status_code == 200
    assert r.json()["version"]["hash_sha256"] == v1["hash_sha256"]


def test_registrar_version_con_hash_explicito():
    v = registrar_version("agente-hash-explicito", autor="test", hash_explicito="a" * 64)
    assert v.hash_sha256 == "a" * 64


def test_registrar_version_sin_config_mantiene_fallback():
    # Compatibilidad: los tests de rf07 llaman registrar_version() pelado;
    # el fallback {"agent_id": ...} sigue produciendo el mismo hash.
    v = registrar_version("agente-hash-fallback", autor="test")
    assert v.hash_sha256 == _hash_config({"agent_id": "agente-hash-fallback"})
