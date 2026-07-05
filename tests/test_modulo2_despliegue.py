"""Tests del Módulo 2 (Despliegue / CI-CD) — RF05, RF06, RF07.

Verifican la lógica con evidencia (no afirmaciones): SSE de despliegue, versionado
inmutable con hash SHA-256, rollback y la regla de promotion (ADMIN para prod).

deploy/rollback exigen token ADMIN; promote exige token válido (prod exige ADMIN).
Los tests mandan un JWT del login stub: admin_a (ADMIN) o viewer_a (VIEWER).
"""
import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AGENTE = "11111111-2222-3333-4444-555555555555"


def _h(usuario: str = "admin_a") -> dict:
    token = client.get("/api/v1/auth/login", params={"usuario": usuario}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_deploy_emite_sse_y_termina_en_done():
    # RF05: el deploy transmite SSE y termina con un frame 'done' exitoso.
    r = client.post(f"/api/v1/agents/{AGENTE}/deploy", headers=_h())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    cuerpo = r.text
    assert '"fase": "build"' in cuerpo
    assert '"fase": "done"' in cuerpo
    assert '"estado": "success"' in cuerpo
    assert '"salud": "healthy"' in cuerpo


def test_deploy_crea_version_inmutable_con_sha256():
    # RF07: un deploy exitoso registra una versión con hash SHA-256 (64 hex).
    client.post(f"/api/v1/agents/{AGENTE}/deploy", headers=_h())
    r = client.get(f"/api/v1/agents/{AGENTE}/versions")
    assert r.status_code == 200
    versiones = r.json()["versions"]
    assert len(versiones) >= 1
    activa = [v for v in versiones if v["estado"] == "activa"]
    assert len(activa) == 1  # exactamente una versión activa
    assert re.fullmatch(r"[0-9a-f]{64}", activa[0]["hash_sha256"])


def test_rollback_genera_version_nueva_sin_borrar():
    # RF07: el rollback NO borra ni modifica; agrega una versión 'rollback'.
    ag = "agente-rollback-test"
    client.post(f"/api/v1/agents/{ag}/deploy", headers=_h())
    client.post(f"/api/v1/agents/{ag}/deploy", headers=_h())
    antes = client.get(f"/api/v1/agents/{ag}/versions").json()["versions"]
    primera = antes[0]["id"]
    r = client.post(f"/api/v1/agents/{ag}/rollback/{primera}", headers=_h())
    assert r.status_code == 200
    assert r.json()["ok"] is True
    despues = client.get(f"/api/v1/agents/{ag}/versions").json()["versions"]
    assert len(despues) == len(antes) + 1          # se agregó, no se borró
    assert despues[-1]["estado"] == "rollback"


def test_rollback_version_inexistente_da_404():
    client.post(f"/api/v1/agents/{AGENTE}/deploy", headers=_h())
    r = client.post(f"/api/v1/agents/{AGENTE}/rollback/no-existe", headers=_h())
    assert r.status_code == 404


def test_promote_a_prod_sin_admin_es_403():
    # RF06: promotion a prod exige rol ADMIN. Con token VIEWER, 403.
    r = client.post(
        f"/api/v1/agents/{AGENTE}/promote",
        headers=_h("viewer_a"),
        json={"ambiente_destino": "prod", "solicitante": "dev1", "rol_solicitante": "DEVELOPER"},
    )
    assert r.status_code == 403


def test_promote_a_prod_con_admin_queda_aprobada():
    r = client.post(
        f"/api/v1/agents/{AGENTE}/promote",
        headers=_h("admin_a"),
        json={"ambiente_destino": "prod", "solicitante": "admin1", "rol_solicitante": "ADMIN"},
    )
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "aprobada"


# --- Casos de borde añadidos en revisión (RF06 / RF07) ---


def test_promote_ambiente_invalido_da_400():
    # RF06: un ambiente fuera de dev/staging/prod se rechaza con 400.
    r = client.post(
        f"/api/v1/agents/{AGENTE}/promote",
        headers=_h("admin_a"),
        json={
            "ambiente_origen": "staging",
            "ambiente_destino": "marte",
            "solicitante": "dev1",
            "rol_solicitante": "ADMIN",
        },
    )
    assert r.status_code == 400


def test_promote_no_prod_sin_admin_queda_pendiente():
    # RF06: promover a un ambiente != prod no exige ADMIN; con token VIEWER
    # queda 'pendiente'.
    r = client.post(
        f"/api/v1/agents/{AGENTE}/promote",
        headers=_h("viewer_a"),
        json={
            "ambiente_origen": "dev",
            "ambiente_destino": "staging",
            "solicitante": "dev1",
            "rol_solicitante": "DEVELOPER",
        },
    )
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "pendiente"


def test_list_environments_devuelve_los_tres():
    r = client.get("/api/v1/agents/environments")
    assert r.status_code == 200
    assert r.json()["environments"] == ["dev", "staging", "prod"]


def test_list_promotions_solo_del_agente():
    ag = "agente-promotions-test"
    client.post(
        f"/api/v1/agents/{ag}/promote",
        headers=_h("viewer_a"),
        json={
            "ambiente_origen": "dev",
            "ambiente_destino": "staging",
            "solicitante": "dev1",
            "rol_solicitante": "DEVELOPER",
        },
    )
    r = client.get(f"/api/v1/agents/{ag}/promotions")
    assert r.status_code == 200
    promos = r.json()["promotions"]
    assert len(promos) == 1
    assert promos[0]["ambiente_destino"] == "staging"


def test_rollback_encadenado_sigue_append_y_una_vigente():
    # RF07: el rollback de un rollback sigue siendo append-only y deja exactamente
    # una versión vigente (activa|rollback).
    ag = "agente-chained-rollback"
    client.post(f"/api/v1/agents/{ag}/deploy", headers=_h())  # v1
    client.post(f"/api/v1/agents/{ag}/deploy", headers=_h())  # v2
    v1 = client.get(f"/api/v1/agents/{ag}/versions").json()["versions"][0]["id"]
    r1 = client.post(f"/api/v1/agents/{ag}/rollback/{v1}", headers=_h())  # v3 (rollback)
    assert r1.status_code == 200
    v3 = r1.json()["version"]["id"]
    r2 = client.post(f"/api/v1/agents/{ag}/rollback/{v3}", headers=_h())  # v4 (rollback de un rollback)
    assert r2.status_code == 200
    versiones = client.get(f"/api/v1/agents/{ag}/versions").json()["versions"]
    assert len(versiones) == 4  # append-only: nada se borró
    vigentes = [v for v in versiones if v["estado"] in ("activa", "rollback")]
    assert len(vigentes) == 1  # exactamente una versión vigente
    assert versiones[-1]["estado"] == "rollback"
