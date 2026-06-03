import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.routers.versions import registrar_version

# Módulo 2 (Despliegue / CI-CD) — RF05: despliegue de 1 clic con log en vivo (SSE).
router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Deployment - Deploy"]
)


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


async def _pipeline(agent_id: str):
    pasos = [
        ("queued", "Despliegue encolado..."),
        ("build", "Construyendo imagen del agente..."),
        ("push", "Subiendo imagen al registry..."),
        ("deploy", "Desplegando contenedor..."),
        ("healthcheck", "Verificando salud del agente..."),
    ]
    for fase, mensaje in pasos:
        yield _evento(fase, mensaje)
        await asyncio.sleep(0.6)

    # RF05 CA-05 + RF07: un despliegue exitoso genera una versión inmutable.
    # (Esto rompe la dependencia circular HU-05 <-> HU-07: el deploy es quien
    # crea la versión.)
    version = registrar_version(agent_id, autor="developer", estado="activa")
    url = f"https://agente-{agent_id[:8]}.agentwatch.app"
    yield _evento(
        "done",
        "Despliegue completo.",
        url=url,
        salud="healthy",
        estado="success",
        version_id=version.id,
    )


@router.post("/{agent_id}/deploy")
async def deploy(agent_id: str):
    # NOTA DE ARQUITECTURA: aquí, para el prototipo académico, el pipeline está
    # simulado (estados reales + timing). En producción (ver ADR-02.1) cada fase
    # invocaría Azure Container Apps (build->push->revision canary) detrás de una
    # interfaz DeploymentProvider; el rollback automático ante fallo de healthcheck
    # se dispararía aquí mismo. El contrato SSE no cambia.
    return StreamingResponse(
        _pipeline(agent_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
