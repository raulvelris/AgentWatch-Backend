"""RF06 — una promoción aprobada mueve la config del agente entre ambientes.

La config por-ambiente que controla el Módulo 2 son las variables de entorno
cifradas (AgentEnvVarDB). Al aprobar una promoción, esas variables se copian del
ambiente origen al destino. Estos tests ejercen el ciclo por la API: PUT en el
origen, promote, GET en el destino. Agentes con id propio para no chocar con los
otros archivos de la suite.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _promote_admin(agente, origen, destino):
    return client.post(
        f"/api/v1/agents/{agente}/promote",
        json={
            "ambiente_origen": origen,
            "ambiente_destino": destino,
            "solicitante": "admin1",
            "rol_solicitante": "ADMIN",
        },
    )


def test_promocion_aprobada_mueve_las_vars():
    ag = "agente-promote-mueve"
    client.put(
        f"/api/v1/agents/{ag}/environments/staging/vars",
        json={"vars": {"OPENAI_KEY": "sk-staging-secreto", "DB_URL": "postgres://staging/db"}},
    )

    r = _promote_admin(ag, "staging", "prod")
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "aprobada"

    staging = client.get(f"/api/v1/agents/{ag}/environments/staging/vars").json()["vars"]
    prod = client.get(f"/api/v1/agents/{ag}/environments/prod/vars").json()["vars"]
    # El destino queda con las mismas variables y el mismo valor (enmascarado).
    assert prod == staging
    assert set(prod) == {"OPENAI_KEY", "DB_URL"}


def test_promocion_pendiente_no_mueve():
    ag = "agente-promote-pendiente"
    client.put(
        f"/api/v1/agents/{ag}/environments/dev/vars",
        json={"vars": {"TOKEN": "valor-dev-secreto"}},
    )

    r = client.post(
        f"/api/v1/agents/{ag}/promote",
        json={
            "ambiente_origen": "dev",
            "ambiente_destino": "staging",
            "solicitante": "dev1",
            "rol_solicitante": "DEVELOPER",
        },
    )
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "pendiente"

    staging = client.get(f"/api/v1/agents/{ag}/environments/staging/vars").json()["vars"]
    assert staging == {}  # una pendiente no mueve nada


def test_upsert_sobrescribe_y_conserva_extras():
    # Decisión upsert: el destino recibe las del origen (sobrescribe las de igual
    # nombre) y conserva las que tuviera aparte.
    ag = "agente-promote-upsert"
    client.put(
        f"/api/v1/agents/{ag}/environments/staging/vars",
        json={"vars": {"SHARED": "valor-de-staging"}},
    )
    client.put(
        f"/api/v1/agents/{ag}/environments/prod/vars",
        json={"vars": {"SHARED": "valor-viejo-de-prod", "SOLO_PROD": "secreto-solo-prod"}},
    )

    r = _promote_admin(ag, "staging", "prod")
    assert r.status_code == 200

    staging = client.get(f"/api/v1/agents/{ag}/environments/staging/vars").json()["vars"]
    prod = client.get(f"/api/v1/agents/{ag}/environments/prod/vars").json()["vars"]
    assert prod["SHARED"] == staging["SHARED"]  # sobrescrita con la de staging
    assert prod["SOLO_PROD"] == "secr***"       # extra del destino, intacta
    assert set(prod) == {"SHARED", "SOLO_PROD"}


def test_origen_sin_vars_es_noop():
    ag = "agente-promote-vacio"
    r = _promote_admin(ag, "staging", "prod")
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "aprobada"

    prod = client.get(f"/api/v1/agents/{ag}/environments/prod/vars").json()["vars"]
    assert prod == {}  # sin nada que mover, la promoción igual pasa


def test_promocion_al_mismo_ambiente_no_rompe():
    # Borde: origen == destino. La copia es un no-op; no se auto-mueve ni duplica.
    ag = "agente-promote-mismo"
    client.put(
        f"/api/v1/agents/{ag}/environments/staging/vars",
        json={"vars": {"K": "valor-cualquiera"}},
    )
    r = _promote_admin(ag, "staging", "staging")
    assert r.status_code == 200

    staging = client.get(f"/api/v1/agents/{ag}/environments/staging/vars").json()["vars"]
    assert set(staging) == {"K"}
