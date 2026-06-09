"""Persistencia del Módulo 2 (Despliegue / CI-CD) — SQLite vía SQLAlchemy.

RF07: la inmutabilidad del historial de versiones está garantizada a nivel
de base de datos con triggers (no por disciplina de código): UPDATE sobre
columnas inmutables y todo DELETE lanzan RAISE(ABORT). El campo `estado`
es el único mutable: es el puntero de ciclo de vida (activa/inactiva/...)
que registrar_version() siempre actualizó.

El engine es perezoso y reiniciable para poder simular un reinicio de
proceso en los tests (nueva instancia sobre el mismo archivo .db).
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        connect_args = {}
        if settings.DATABASE_URL.startswith("sqlite"):
            # FastAPI atiende requests en un threadpool: la conexión SQLite
            # puede usarse desde otro hilo distinto al que la creó.
            connect_args["check_same_thread"] = False
        _engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
    return _engine


def get_session() -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory()


def reiniciar_engine():
    """Descarta el engine cacheado. Simula un reinicio de proceso en tests:
    la siguiente sesión abre una conexión nueva sobre el mismo archivo."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


# RF07: triggers de inmutabilidad. UPDATE solo se permite sobre `estado`
# (puntero de ciclo de vida); cualquier cambio a las columnas de contenido
# y cualquier DELETE abortan a nivel de BD.
_TRIGGER_VERSIONES_SIN_UPDATE = """
CREATE TRIGGER IF NOT EXISTS versiones_sin_update
BEFORE UPDATE ON versiones
FOR EACH ROW
WHEN OLD.id <> NEW.id
   OR OLD.agent_id <> NEW.agent_id
   OR OLD.numero <> NEW.numero
   OR OLD.fecha <> NEW.fecha
   OR OLD.autor <> NEW.autor
   OR OLD.hash_sha256 <> NEW.hash_sha256
   OR OLD.descripcion <> NEW.descripcion
BEGIN
    SELECT RAISE(ABORT,
        'RF07: las versiones son inmutables; solo `estado` puede cambiar');
END;
"""

_TRIGGER_VERSIONES_SIN_DELETE = """
CREATE TRIGGER IF NOT EXISTS versiones_sin_delete
BEFORE DELETE ON versiones
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT,
        'RF07: el historial de versiones es append-only; DELETE bloqueado');
END;
"""


def init_db():
    """Seed idempotente: crea tablas y triggers si no existen.

    El Módulo 2 no tiene filas demo que sembrar (el historial empieza
    vacío legítimamente): el "estado limpio inicial" es el schema con sus
    triggers, y se regenera solo al arrancar sobre un archivo nuevo.
    """
    import app.models  # noqa: F401  (registra los modelos en Base.metadata)

    engine = get_engine()
    Base.metadata.create_all(engine)
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(text(_TRIGGER_VERSIONES_SIN_UPDATE))
            conn.execute(text(_TRIGGER_VERSIONES_SIN_DELETE))
