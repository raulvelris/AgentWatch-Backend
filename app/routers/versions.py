import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.database import get_session
from app.models import VersionDB
from app.schemas.version import Version
from app.services.deps import require_admin

# Módulo 2 (Despliegue / CI-CD) — RF07: versionado inmutable con rollback.
router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Deployment - Versions"]
)

# Persistencia en SQLite (tabla `versiones`). Inmutabilidad (RF07) garantizada
# a nivel de BD: triggers BEFORE UPDATE/DELETE con RAISE(ABORT) — ver
# app/core/database.py (ADR-02.4 / 4.2 de la documentación). El historial
# sobrevive reinicios del proceso.


def _hash_config(agent_id: str, numero: int, ts: str) -> str:
    payload = json.dumps(
        {"agent_id": agent_id, "numero": numero, "ts": ts},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _a_schema(v: VersionDB) -> Version:
    return Version(
        id=v.id,
        numero=v.numero,
        fecha=v.fecha,
        autor=v.autor,
        hash_sha256=v.hash_sha256,
        estado=v.estado,
        descripcion=v.descripcion,
    )


def registrar_version(
    agent_id: str,
    autor: str,
    estado: str = "activa",
    descripcion: str = "",
) -> Version:
    """Crea y agrega una versión nueva (append-only: nunca se borra del historial).
    El CONTENIDO de las versiones previas es inmutable —id, numero, fecha, autor y
    hash_sha256 no cambian; lo refuerzan los triggers de la BD—; solo se actualiza
    el puntero de ciclo de vida `estado` (la anterior 'activa'/'rollback' pasa a
    'inactiva') para que haya una sola versión vigente."""
    # Reintento acotado ante colisión de PK: dos deploys concurrentes del mismo
    # agente pueden calcular el mismo `numero` (len+1) y chocar en el id
    # `{agent_id}-v{numero}` al commitear. En vez de un 500, se recomputa con el
    # historial fresco y se reintenta (mismo patrón que governance.crear_politica).
    # La race es rara (threadpool de FastAPI); 5 intentos sobran.
    for _ in range(5):
        with get_session() as session:
            historial = (
                session.query(VersionDB)
                .filter(VersionDB.agent_id == agent_id)
                .order_by(VersionDB.numero)
                .all()
            )
            for v in historial:
                if v.estado in ("activa", "rollback"):
                    v.estado = "inactiva"
            numero = len(historial) + 1
            ts = datetime.now(timezone.utc).isoformat()
            version = VersionDB(
                id=f"{agent_id}-v{numero}",
                agent_id=agent_id,
                numero=numero,
                fecha=ts,
                autor=autor,
                hash_sha256=_hash_config(agent_id, numero, ts),
                estado=estado,
                descripcion=descripcion,
            )
            session.add(version)
            try:
                session.commit()
            except IntegrityError:
                # Otro deploy ganó este `numero`; recomputar y reintentar.
                session.rollback()
                continue
            return _a_schema(version)
    raise HTTPException(
        status_code=409,
        detail="No se pudo asignar número de versión por colisión concurrente; reintentar",
    )


def version_activa(agent_id: str) -> Version | None:
    """Versión vigente del agente ('activa' o 'rollback'), si existe.
    La usa el deploy (RF05) para conocer la versión de origen y para el
    revert automático ante fallo."""
    with get_session() as session:
        v = (
            session.query(VersionDB)
            .filter(
                VersionDB.agent_id == agent_id,
                VersionDB.estado.in_(("activa", "rollback")),
            )
            .order_by(VersionDB.numero.desc())
            .first()
        )
        return _a_schema(v) if v else None


def cambiar_estado(version_id: str, estado: str) -> None:
    """Mueve el puntero de ciclo de vida de una versión (único campo mutable
    según RF07; los triggers bloquean cualquier otro cambio). La usa el
    revert automático del deploy (RF05)."""
    with get_session() as session:
        v = session.get(VersionDB, version_id)
        if v is not None:
            v.estado = estado
            session.commit()


@router.get("/{agent_id}/versions")
def list_versions(agent_id: str):
    with get_session() as session:
        historial = (
            session.query(VersionDB)
            .filter(VersionDB.agent_id == agent_id)
            .order_by(VersionDB.numero)
            .all()
        )
        return {"versions": [_a_schema(v) for v in historial]}


@router.post("/{agent_id}/rollback/{version_id}", dependencies=[Depends(require_admin)])
def rollback(agent_id: str, version_id: str):
    with get_session() as session:
        objetivo = (
            session.query(VersionDB)
            .filter(VersionDB.agent_id == agent_id, VersionDB.id == version_id)
            .first()
        )
    if objetivo is None:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    # RF07: el rollback NO modifica ni borra versiones; genera una versión nueva
    # marcada como 'rollback' que apunta a la versión objetivo.
    nueva = registrar_version(
        agent_id,
        autor="rollback",
        estado="rollback",
        descripcion=f"rollback to {objetivo.id}",
    )
    return {"ok": True, "version": nueva, "rollback_a": objetivo.id}
