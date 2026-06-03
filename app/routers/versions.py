import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas.version import Version

# Módulo 2 (Despliegue / CI-CD) — RF07: versionado inmutable con rollback.
router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Deployment - Versions"]
)

# Almacenamiento en memoria (mismo estilo que agents_db/templates_db).
# Inmutabilidad (RF07): solo se hace append; ningún endpoint modifica ni elimina
# una versión existente. En un backend con BD esto se reforzaría con un trigger
# NOT UPDATE / NOT DELETE (ver ADR-02.4 / 4.2 de la documentación).
versions_db: dict[str, list[Version]] = {}


def _hash_config(agent_id: str, numero: int, ts: str) -> str:
    payload = json.dumps(
        {"agent_id": agent_id, "numero": numero, "ts": ts},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def registrar_version(
    agent_id: str,
    autor: str,
    estado: str = "activa",
    descripcion: str = "",
) -> Version:
    """Crea y agrega una versión nueva (append-only: nunca se borra del historial).
    El CONTENIDO de las versiones previas es inmutable —id, numero, fecha, autor y
    hash_sha256 no cambian—; solo se actualiza el puntero de ciclo de vida `estado`
    (la anterior 'activa'/'rollback' pasa a 'inactiva') para que haya una sola
    versión vigente."""
    historial = versions_db.setdefault(agent_id, [])
    for v in historial:
        if v.estado in ("activa", "rollback"):
            v.estado = "inactiva"
    numero = len(historial) + 1
    ts = datetime.now(timezone.utc).isoformat()
    version = Version(
        id=f"{agent_id}-v{numero}",
        numero=numero,
        fecha=ts,
        autor=autor,
        hash_sha256=_hash_config(agent_id, numero, ts),
        estado=estado,
        descripcion=descripcion,
    )
    historial.append(version)
    return version


@router.get("/{agent_id}/versions")
def list_versions(agent_id: str):
    return {"versions": versions_db.get(agent_id, [])}


@router.post("/{agent_id}/rollback/{version_id}")
def rollback(agent_id: str, version_id: str):
    historial = versions_db.get(agent_id, [])
    objetivo = next((v for v in historial if v.id == version_id), None)
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
