"""Cierre de auth del Módulo 2: deploy, rollback y env_vars PUT/DELETE exigen
token ADMIN (401 sin token, 403 con VIEWER); promote exige token válido y el
destino prod exige ADMIN. Cuerpos válidos, así el único motivo de fallo es la auth.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.util_agentes import crear_agente

client = TestClient(app)

AG = "agente-auth-cierre"


def _tok(usuario: str) -> dict:
    token = client.get("/api/v1/auth/login", params={"usuario": usuario}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# --- deploy: ADMIN ---
def test_deploy_anonimo_da_401():
    assert client.post(f"/api/v1/agents/{AG}/deploy").status_code == 401


def test_deploy_viewer_da_403():
    r = client.post(f"/api/v1/agents/{AG}/deploy", headers=_tok("viewer_a"))
    assert r.status_code == 403


def test_deploy_admin_funciona(sin_sleep):
    # Agente real: con ADMIN el deploy tiene que llegar al pipeline (200).
    agente = crear_agente(client)
    r = client.post(f"/api/v1/agents/{agente}/deploy", headers=_tok("admin_a"))
    assert r.status_code == 200


# --- rollback: ADMIN (con auth pasa; el 404 prueba que llegó al endpoint) ---
def test_rollback_anonimo_da_401():
    assert client.post(f"/api/v1/agents/{AG}/rollback/x").status_code == 401


def test_rollback_viewer_da_403():
    r = client.post(f"/api/v1/agents/{AG}/rollback/x", headers=_tok("viewer_a"))
    assert r.status_code == 403


def test_rollback_admin_pasa_la_auth():
    r = client.post(f"/api/v1/agents/{AG}/rollback/no-existe", headers=_tok("admin_a"))
    assert r.status_code == 404  # auth OK; falla por versión inexistente, no por auth


# --- promote: token válido; prod exige ADMIN ---
def _cuerpo(destino="prod"):
    return {
        "ambiente_origen": "staging",
        "ambiente_destino": destino,
        "solicitante": "quien-sea",
        "rol_solicitante": "ADMIN",
    }


def test_promote_anonimo_da_401():
    assert client.post(f"/api/v1/agents/{AG}/promote", json=_cuerpo()).status_code == 401


def test_promote_prod_viewer_da_403():
    r = client.post(f"/api/v1/agents/{AG}/promote", headers=_tok("viewer_a"), json=_cuerpo("prod"))
    assert r.status_code == 403


def test_promote_prod_admin_aprueba():
    r = client.post(f"/api/v1/agents/{AG}/promote", headers=_tok("admin_a"), json=_cuerpo("prod"))
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "aprobada"


def test_promote_staging_viewer_queda_pendiente():
    # Un VIEWER autenticado sí puede pedir una promoción no-prod: queda pendiente.
    r = client.post(
        f"/api/v1/agents/{AG}/promote", headers=_tok("viewer_a"),
        json={"ambiente_origen": "dev", "ambiente_destino": "staging", "solicitante": "v"},
    )
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "pendiente"


# --- env_vars PUT/DELETE: ADMIN. GET abierto ---
def test_put_vars_anonimo_da_401():
    r = client.put(f"/api/v1/agents/{AG}/environments/dev/vars", json={"vars": {"K": "v"}})
    assert r.status_code == 401


def test_put_vars_viewer_da_403():
    r = client.put(
        f"/api/v1/agents/{AG}/environments/dev/vars",
        headers=_tok("viewer_a"),
        json={"vars": {"K": "v"}},
    )
    assert r.status_code == 403


def test_delete_vars_anonimo_da_401():
    assert client.delete(f"/api/v1/agents/{AG}/environments/dev/vars/K").status_code == 401


def test_get_vars_sigue_abierto():
    # El GET (enmascarado) no exige token.
    r = client.get(f"/api/v1/agents/{AG}/environments/dev/vars")
    assert r.status_code == 200
