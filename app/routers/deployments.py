import asyncio
import json
from app.routers.agents import obtener_agente_por_id
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.database import get_session
from app.models import DeploymentRecordDB
from app.routers.versions import cambiar_estado, registrar_version, version_activa
from app.services.deps import require_admin
from app.services.notificaciones import encolar_notificacion

# Módulo 2 (Despliegue / CI-CD) — RF05: despliegue de 1 clic con log en vivo (SSE).
router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Deployment - Deploy"]
)

PASOS = [
    ("queued", "Despliegue encolado..."),
    ("build", "Construyendo imagen del agente..."),
    ("push", "Subiendo imagen al registry..."),
    ("deploy", "Desplegando contenedor..."),
    ("healthcheck", "Verificando salud del agente..."),
]

FASES_VALIDAS = {fase for fase, _ in PASOS}


def _evento(fase: str, mensaje: str, **extra) -> str:
    """Serializa un evento como frame SSE: `data: {json}\\n\\n`.
    Coincide con el tipo EventoDespliegue del frontend y con
    docs/contrato-modulo2-despliegue.md."""
    evento = {
        "fase": fase,
        "mensaje": mensaje,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    evento.update(extra)
    return f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"


def _registrar_despliegue(
    agent_id: str,
    autor: str,
    version_origen: str | None,
    version_desplegada: str | None,
    resultado: str,
    fase_fallo: str | None,
) -> None:
    """RF05: TODO despliegue (exitoso o fallido) deja registro auditable:
    quién, cuándo, desde qué versión y con qué resultado."""
    with get_session() as session:
        session.add(
            DeploymentRecordDB(
                agent_id=agent_id,
                autor=autor,
                fecha=datetime.now(timezone.utc).isoformat(),
                version_origen=version_origen,
                version_desplegada=version_desplegada,
                resultado=resultado,
                fase_fallo=fase_fallo,
            )
        )
        session.commit()


async def _pipeline(agent_id: str, autor: str, fallo: str | None, configuracion: dict):
    # La config llega resuelta desde el handler: levantar un HTTPException
    # acá adentro ya no sirve (los headers 200 del stream ya se enviaron).
    origen = version_activa(agent_id)

    # RF05 CA-05 + RF07: el deploy crea la versión candidata al inicio
    # (la previa pasa a 'inactiva'); así el fallo tiene algo que revertir.
    candidata = registrar_version(
        agent_id,
        autor=autor,
        estado="activa",
        configuracion=configuracion,
    )

    for fase, mensaje in PASOS:
        if fallo == fase:
            # Camino de fallo determinista (simulado vía ?fallo=<fase>).
            yield _evento(
                fase,
                f"Error en la fase '{fase}': el healthcheck/paso no superó la verificación (fallo simulado).",
                estado="error",
            )
            # Revert automático: la candidata queda marcada 'fallida' y la
            # versión previa recupera su estado vigente.
            cambiar_estado(candidata.id, "fallida")
            if origen is not None:
                cambiar_estado(origen.id, origen.estado)
                mensaje_revert = (
                    f"Revert automático: la versión {origen.id} vuelve a estar vigente."
                )
            else:
                mensaje_revert = (
                    "Revert automático: no había versión previa vigente que restaurar."
                )
            yield _evento(
                "revert",
                mensaje_revert,
                version_restaurada=origen.id if origen else None,
            )
            yield _evento(
                "done",
                "Despliegue fallido.",
                estado="failed",
                version_id=candidata.id,
                fase_fallo=fase,
            )
            _registrar_despliegue(
                agent_id,
                autor,
                origen.id if origen else None,
                candidata.id,
                "failed",
                fase,
            )
            encolar_notificacion(
                "deploy_fallido",
                "ADMIN",
                f"Deploy del agente {agent_id} falló en la fase '{fase}'; "
                f"revert automático aplicado.",
                agent_id=agent_id,
            )
            return
        yield _evento(fase, mensaje)
        await asyncio.sleep(0.6)

    url = f"https://agente-{agent_id[:8]}.agentwatch.app"
    yield _evento(
        "done",
        "Despliegue completo.",
        url=url,
        salud="healthy",
        estado="success",
        version_id=candidata.id,
    )
    _registrar_despliegue(
        agent_id,
        autor,
        origen.id if origen else None,
        candidata.id,
        "success",
        None,
    )


@router.post("/{agent_id}/deploy")
async def deploy(
    agent_id: str,
    fallo: str | None = None,
    claims: dict = Depends(require_admin),
):
    # NOTA DE ARQUITECTURA: aquí, para el prototipo académico, el pipeline está
    # simulado (estados reales + timing). En producción (ver ADR-02.1) cada fase
    # invocaría Azure Container Apps (build->push->revision canary) detrás de una
    # interfaz DeploymentProvider. El contrato SSE no cambia.
    #
    # ?fallo=<fase> fuerza un fallo determinista en esa fase para demostrar
    # el camino de error + revert automático (RF05). Sin el parámetro, el
    # deploy es el flujo normal de siempre.
    if fallo is not None and fallo not in FASES_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Fase de fallo inválida; usar una de: {sorted(FASES_VALIDAS)}",
        )
    # RF07: la config real del agente se resuelve ANTES de abrir el stream.
    # Si el agente no existe, el cliente recibe un 404 JSON limpio; adentro
    # del generador ya era tarde (headers 200 enviados, stream roto).
    agente = obtener_agente_por_id(agent_id)
    if agente is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró la configuración del agente",
        )
    # RF05 'quién': el deploy exige token ADMIN (require_admin), así que el autor
    # sale del claim `sub` del JWT. El fallback "developer" queda por si el claim
    # viniera sin sub.
    autor = claims.get("sub", "developer")
    return StreamingResponse(
        _pipeline(agent_id, autor, fallo, agente.model_dump(mode="json")),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{agent_id}/deployments")
def list_deployments(agent_id: str):
    """RF05: historial auditable de despliegues del agente."""
    with get_session() as session:
        registros = (
            session.query(DeploymentRecordDB)
            .filter(DeploymentRecordDB.agent_id == agent_id)
            .order_by(DeploymentRecordDB.id)
            .all()
        )
        return {
            "deployments": [
                {
                    "id": r.id,
                    "agent_id": r.agent_id,
                    "autor": r.autor,
                    "fecha": r.fecha,
                    "version_origen": r.version_origen,
                    "version_desplegada": r.version_desplegada,
                    "resultado": r.resultado,
                    "fase_fallo": r.fase_fallo,
                }
                for r in registros
            ]
        }
