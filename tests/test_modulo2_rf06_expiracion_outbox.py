"""RF06: expiración de solicitudes a las 24h (reloj inyectable), precedencia
del JWT sobre el rol del body y outbox de notificaciones filtrable."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services import reloj

client = TestClient(app)


def _h(usuario: str = "viewer_a") -> dict:
    """Token en el header. promote exige token válido; dev/staging por VIEWER
    queda 'pendiente'."""
    token = client.get("/api/v1/auth/login", params={"usuario": usuario}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_promotion_pendiente_expira_a_las_24h(monkeypatch):
    agente = "agente-expira-24h"
    respuesta = client.post(
        f"/api/v1/agents/{agente}/promote",
        headers=_h(),
        json={
            "ambiente_origen": "dev",
            "ambiente_destino": "staging",
            "solicitante": "dev-uno",
            "rol_solicitante": "DEVELOPER",
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["promotion"]["estado"] == "pendiente"

    # Recién creada: sigue pendiente.
    promociones = client.get(f"/api/v1/agents/{agente}/promotions").json()["promotions"]
    assert promociones[0]["estado"] == "pendiente"

    # Reloj inyectable: 25 horas después, la consulta la marca expirada.
    futuro = reloj.ahora_utc() + timedelta(hours=25)
    monkeypatch.setattr(reloj, "ahora_utc", lambda: futuro)

    promociones = client.get(f"/api/v1/agents/{agente}/promotions").json()["promotions"]
    assert promociones[0]["estado"] == "expirada"

    # La expiración queda notificada en el outbox.
    notificaciones = client.get(
        "/api/v1/notifications/",
        params={"tipo": "promotion_expirada", "agent_id": agente},
    ).json()["notifications"]
    assert len(notificaciones) == 1


def test_promotion_pendiente_notifica_al_admin():
    agente = "agente-notifica-admin"
    client.post(
        f"/api/v1/agents/{agente}/promote",
        headers=_h(),
        json={
            "ambiente_origen": "dev",
            "ambiente_destino": "staging",
            "solicitante": "dev-dos",
            "rol_solicitante": "DEVELOPER",
        },
    )
    notificaciones = client.get(
        "/api/v1/notifications/",
        params={
            "tipo": "promotion_pendiente",
            "agent_id": agente,
            "destinatario_rol": "ADMIN",
        },
    ).json()["notifications"]
    assert len(notificaciones) == 1
    assert "espera aprobación" in notificaciones[0]["mensaje"]


def test_jwt_tiene_precedencia_sobre_el_rol_del_body():
    # Un VIEWER autenticado no puede promover a prod aunque el body
    # autodeclare ADMIN: el rol sale del claim del token; el `rol_solicitante`
    # del body ya no se usa.
    agente = "agente-precedencia-jwt"
    token = client.get("/api/v1/auth/login", params={"usuario": "viewer_a"}).json()["token"]
    respuesta = client.post(
        f"/api/v1/agents/{agente}/promote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ambiente_origen": "staging",
            "ambiente_destino": "prod",
            "solicitante": "impostor",
            "rol_solicitante": "ADMIN",
        },
    )
    assert respuesta.status_code == 403


def test_admin_con_jwt_promueve_a_prod_y_queda_aprobada():
    agente = "agente-admin-jwt"
    token = client.get("/api/v1/auth/login", params={"usuario": "admin_a"}).json()["token"]
    respuesta = client.post(
        f"/api/v1/agents/{agente}/promote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ambiente_origen": "staging",
            "ambiente_destino": "prod",
            "solicitante": "ignorado-por-el-token",
            "rol_solicitante": "DEVELOPER",
        },
    )
    assert respuesta.status_code == 200
    promotion = respuesta.json()["promotion"]
    assert promotion["estado"] == "aprobada"
    # Identidad real del token, no la del body.
    assert promotion["solicitante"] == "admin_a"
    assert promotion["aprobado_por"] == "admin_a"
