"""RF05: camino de fallo determinista (?fallo=<fase>) con revert automático
y registro auditable de TODO despliegue (quién/cuándo/origen/resultado)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _h(usuario: str = "admin_a") -> dict:
    """Token en el header. deploy ahora exige ADMIN (require_admin)."""
    token = client.get("/api/v1/auth/login", params={"usuario": usuario}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_deploy_exitoso_persiste_deployment_record():
    # RF05: hasta un deploy exitoso deja registro (autor, fecha, resultado).
    agente = "agente-record-exitoso"
    respuesta = client.post(f"/api/v1/agents/{agente}/deploy", headers=_h())
    assert respuesta.status_code == 200

    registros = client.get(f"/api/v1/agents/{agente}/deployments").json()["deployments"]
    assert len(registros) == 1
    registro = registros[0]
    assert registro["resultado"] == "success"
    assert registro["autor"] == "admin_a"  # autor = claim sub del token ADMIN
    assert registro["version_desplegada"] == f"{agente}-v1"
    assert registro["version_origen"] is None  # primer deploy: sin versión previa
    assert registro["fecha"]


def test_deploy_con_fallo_emite_error_revert_y_failed():
    agente = "agente-fallo-revert"
    # Primer deploy exitoso deja v1 activa.
    client.post(f"/api/v1/agents/{agente}/deploy", headers=_h())

    # Segundo deploy falla en healthcheck: SSE narra error -> revert -> failed.
    respuesta = client.post(
        f"/api/v1/agents/{agente}/deploy?fallo=healthcheck", headers=_h()
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.text
    assert '"estado": "error"' in cuerpo
    assert '"fase": "revert"' in cuerpo
    assert '"estado": "failed"' in cuerpo
    assert f'"version_restaurada": "{agente}-v1"' in cuerpo

    # Revert automático: v1 vuelve a estar activa; la candidata v2 queda
    # 'fallida'; sigue habiendo UNA sola versión vigente.
    versiones = client.get(f"/api/v1/agents/{agente}/versions").json()["versions"]
    por_id = {v["id"]: v for v in versiones}
    assert por_id[f"{agente}-v1"]["estado"] == "activa"
    assert por_id[f"{agente}-v2"]["estado"] == "fallida"
    vigentes = [v for v in versiones if v["estado"] in ("activa", "rollback")]
    assert len(vigentes) == 1

    # Registro del fallo: resultado, fase y versión de origen.
    registros = client.get(f"/api/v1/agents/{agente}/deployments").json()["deployments"]
    assert len(registros) == 2
    fallido = registros[-1]
    assert fallido["resultado"] == "failed"
    assert fallido["fase_fallo"] == "healthcheck"
    assert fallido["version_origen"] == f"{agente}-v1"

    # El fallo encola notificación en el outbox (RF05/RF06).
    notificaciones = client.get(
        "/api/v1/notifications/",
        params={"tipo": "deploy_fallido", "agent_id": agente},
    ).json()["notifications"]
    assert len(notificaciones) == 1
    assert "revert" in notificaciones[0]["mensaje"]


def test_deploy_fallo_en_fase_invalida_da_400():
    respuesta = client.post(
        "/api/v1/agents/agente-x/deploy?fallo=meteorito", headers=_h()
    )
    assert respuesta.status_code == 400


def test_deploy_con_jwt_registra_al_autor_real():
    # RF05 'quién': con Authorization: Bearer, el autor sale del claim sub.
    agente = "agente-autor-jwt"
    token = client.get("/api/v1/auth/login", params={"usuario": "admin_a"}).json()["token"]
    respuesta = client.post(
        f"/api/v1/agents/{agente}/deploy",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 200
    registros = client.get(f"/api/v1/agents/{agente}/deployments").json()["deployments"]
    assert registros[0]["autor"] == "admin_a"


def test_deploy_con_token_invalido_da_401():
    respuesta = client.post(
        "/api/v1/agents/agente-x/deploy",
        headers={"Authorization": "Bearer token-falso"},
    )
    assert respuesta.status_code == 401
