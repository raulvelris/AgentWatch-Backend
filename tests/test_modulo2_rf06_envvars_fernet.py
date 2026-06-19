"""RF06/ADR-02.6 — Variables de entorno por ambiente cifradas con Fernet.

Verifica EC-02.5: la BD solo contiene ciphertext y la API solo expone valores
enmascarados. Sigue el patrón del Módulo 2 (TestClient a nivel de módulo + BD
temporal del conftest; verificación con SQL crudo como en
test_modulo2_rf07_inmutabilidad.py — el evaluador puede correr ese SELECT en vivo).
"""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import database
from app.main import app

client = TestClient(app)

AGENTE = "agente-envvars"


def test_put_env_vars_guarda_cifrado():
    # EC-02.5: tras un PUT, valor_cifrado NO contiene el texto plano.
    secreto = "sk-super-secreto-1234"
    r = client.put(
        f"/api/v1/agents/{AGENTE}/environments/dev/vars",
        json={"vars": {"OPENAI_KEY": secreto}},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "guardadas": 1}

    # SQL crudo contra SQLite: lo que un atacante con acceso a la BD vería.
    engine = database.get_engine()
    with engine.connect() as conexion:
        valor = conexion.execute(
            text(
                "SELECT valor_cifrado FROM agent_env_vars "
                "WHERE agent_id = :a AND ambiente = 'dev' AND nombre = 'OPENAI_KEY'"
            ),
            {"a": AGENTE},
        ).scalar_one()
    assert valor != secreto  # nunca el plano
    assert secreto not in valor  # ni como substring
    assert valor.startswith("gAAA")  # token Fernet (base64 urlsafe)


def test_get_env_vars_devuelve_enmascarado():
    secreto = "postgresql://user:pass@host/db"
    client.put(
        f"/api/v1/agents/{AGENTE}/environments/staging/vars",
        json={"vars": {"DATABASE_URL": secreto}},
    )
    r = client.get(f"/api/v1/agents/{AGENTE}/environments/staging/vars")
    assert r.status_code == 200
    vars_ = r.json()["vars"]
    assert "DATABASE_URL" in vars_
    enmascarado = vars_["DATABASE_URL"]
    assert enmascarado != secreto  # nunca el plano completo
    assert enmascarado.endswith("***")  # enmascarado
    assert len(enmascarado) <= len("post") + 3  # a lo sumo 4 chars + ***


def test_env_invalido_devuelve_400():
    r_put = client.put(
        f"/api/v1/agents/{AGENTE}/environments/produccion/vars",
        json={"vars": {"X": "y"}},
    )
    assert r_put.status_code == 400
    r_get = client.get(f"/api/v1/agents/{AGENTE}/environments/produccion/vars")
    assert r_get.status_code == 400


def test_put_sin_vars_dict_devuelve_400():
    r = client.put(
        f"/api/v1/agents/{AGENTE}/environments/dev/vars",
        json={"otra_cosa": 1},
    )
    assert r.status_code == 400


def test_delete_env_var():
    client.put(
        f"/api/v1/agents/{AGENTE}/environments/dev/vars",
        json={"vars": {"BORRABLE": "valor-temporal"}},
    )
    r_del = client.delete(f"/api/v1/agents/{AGENTE}/environments/dev/vars/BORRABLE")
    assert r_del.status_code == 200
    assert r_del.json() == {"ok": True}

    # GET posterior: la variable ya no aparece.
    vars_ = client.get(
        f"/api/v1/agents/{AGENTE}/environments/dev/vars"
    ).json()["vars"]
    assert "BORRABLE" not in vars_


def test_delete_inexistente_devuelve_404():
    r = client.delete(f"/api/v1/agents/{AGENTE}/environments/dev/vars/NO_EXISTE")
    assert r.status_code == 404


def test_upsert_sobreescribe_sin_duplicar():
    # Mismo nombre dos veces: el segundo PUT actualiza, no duplica (UniqueConstraint).
    client.put(
        f"/api/v1/agents/{AGENTE}/environments/prod/vars",
        json={"vars": {"TOKEN": "valor-1"}},
    )
    client.put(
        f"/api/v1/agents/{AGENTE}/environments/prod/vars",
        json={"vars": {"TOKEN": "valor-2-distinto"}},
    )
    engine = database.get_engine()
    with engine.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT valor_cifrado FROM agent_env_vars "
                "WHERE agent_id = :a AND ambiente = 'prod' AND nombre = 'TOKEN'"
            ),
            {"a": AGENTE},
        ).fetchall()
    assert len(filas) == 1  # una sola fila: upsert, no duplicado
