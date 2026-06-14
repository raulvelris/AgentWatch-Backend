"""RF07: inmutabilidad garantizada A NIVEL DE BD (triggers SQLite) y
persistencia del historial tras un reinicio del proceso."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import database
from app.main import app
from app.routers.versions import registrar_version

client = TestClient(app)


def test_update_de_contenido_por_sql_crudo_es_bloqueado_por_trigger():
    version = registrar_version("agente-inmutable", autor="enzo")
    engine = database.get_engine()
    with pytest.raises(IntegrityError, match="RF07"):
        with engine.begin() as conexion:
            conexion.execute(
                text("UPDATE versiones SET hash_sha256 = 'manipulado' WHERE id = :id"),
                {"id": version.id},
            )


def test_delete_por_sql_crudo_es_bloqueado_por_trigger():
    version = registrar_version("agente-sin-delete", autor="enzo")
    engine = database.get_engine()
    with pytest.raises(IntegrityError, match="RF07"):
        with engine.begin() as conexion:
            conexion.execute(
                text("DELETE FROM versiones WHERE id = :id"),
                {"id": version.id},
            )


def test_update_del_estado_si_esta_permitido():
    # `estado` es el puntero de ciclo de vida (activa/inactiva/...): es el
    # ÚNICO campo que el trigger deja mutar (registrar_version depende de eso).
    version = registrar_version("agente-ciclo-vida", autor="enzo")
    engine = database.get_engine()
    with engine.begin() as conexion:
        conexion.execute(
            text("UPDATE versiones SET estado = 'inactiva' WHERE id = :id"),
            {"id": version.id},
        )
    versiones = client.get("/api/v1/agents/agente-ciclo-vida/versions").json()["versions"]
    assert versiones[0]["estado"] == "inactiva"


def test_historial_sobrevive_un_reinicio_del_proceso():
    agente = "agente-reinicio"
    version = registrar_version(agente, autor="enzo", descripcion="antes del reinicio")

    # Simula el reinicio: se descarta el engine (conexiones incluidas) y se
    # vuelve a inicializar sobre EL MISMO archivo .db.
    database.reiniciar_engine()
    database.init_db()

    versiones = client.get(f"/api/v1/agents/{agente}/versions").json()["versions"]
    assert [v["id"] for v in versiones] == [version.id]
    assert versiones[0]["descripcion"] == "antes del reinicio"
    assert versiones[0]["hash_sha256"] == version.hash_sha256
