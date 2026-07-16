import json
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import redis

from app.core.database import get_session
from app.models import AgentDB
from app.schemas.agent import AgentConfig
from app.core.redis_client import redis_db

logger = logging.getLogger(__name__)

class StateUpdate(BaseModel):
    estado: str


router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Agents"],
)


def _a_schema(agent: AgentDB) -> AgentConfig:
    """Convierte el registro SQLite al schema utilizado por la API."""
    datos = json.loads(agent.config_json)
    datos["id"] = agent.id
    datos["nombre"] = agent.nombre
    datos["tipo"] = agent.tipo
    datos["estado"] = agent.estado
    datos["tenant_id"] = agent.tenant_id
    datos["owner"] = agent.owner

    return AgentConfig(**datos)


def obtener_agente_por_id(agent_id: str) -> AgentConfig | None:
    """Permite que despliegue y versionado lean la configuración real."""
    with get_session() as session:
        agent = session.get(AgentDB, agent_id)
        return _a_schema(agent) if agent else None


def listar_agentes() -> list[AgentConfig]:
    with get_session() as session:
        agentes = session.query(AgentDB).order_by(AgentDB.nombre).all()
        return [_a_schema(agent) for agent in agentes]


def _guardar_agent_config(agent: AgentConfig) -> AgentDB:
    """Guarda la configuración completa en formato JSON."""
    config = agent.model_dump(mode="json")

    return AgentDB(
        id=str(agent.id),
        tenant_id=agent.tenant_id,
        owner=agent.owner,
        nombre=agent.nombre,
        tipo=agent.tipo,
        estado=agent.estado,
        config_json=json.dumps(
            config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def _crear_agentes_demo_si_no_existen() -> None:
    """Conserva los agentes demo que antes vivían en la lista en memoria."""
    agentes_demo = [
        AgentConfig(
            id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            nombre="Soporte Nivel 1",
            tipo="Customer Service",
            proposito="Atención de consultas básicas",
            fuente="Knowledge Base",
            descripcion_fuente="Docs internos",
            regla="No insultar",
            supervision="Human-in-the-loop",
            estado="ACTIVE",
        ),
        AgentConfig(
            id=uuid.UUID("87654321-4321-8765-4321-876543210987"),
            nombre="Analista de Datos",
            tipo="Data Analysis",
            proposito="Procesar reportes financieros",
            fuente="Data Warehouse",
            descripcion_fuente="BBDD SQL",
            regla="No filtrar PII",
            supervision="Automática",
            estado="PAUSED",
        ),
    ]

    with get_session() as session:
        for agent in agentes_demo:
            if session.get(AgentDB, str(agent.id)) is None:
                session.add(_guardar_agent_config(agent))
        session.commit()


# La siembra se invoca desde app/main.py DESPUÉS de init_db(): a nivel de
# import de este módulo las tablas todavía no existen y una BD fresca moría
# con "no such table: agents" antes de poder arrancar.


@router.post("/")
def create_agent(agent: AgentConfig):
    """Crea un agente y aplica la invalidación del patrón Cache-Aside."""
    with get_session() as session:
        if session.get(AgentDB, str(agent.id)) is not None:
            raise HTTPException(
                status_code=409,
                detail="Ya existe un agente con ese ID",
            )

        registro = _guardar_agent_config(agent)
        session.add(registro)
        session.commit()
        
        agent_creado = _a_schema(registro)

        # PASO 4 (Cache-Aside): Invalidar caché al modificar datos
        if redis_db is not None:
            try:
                redis_db.delete("agents_list_all")
            except Exception:
                pass

        return {
            "message": "Agente creado correctamente",
            "agent": agent_creado,
        }


@router.get("/")
def list_agents():
    """
    Implementación del patrón arquitectónico Cache-Aside.
    Optimiza el CA-03 de la HU-21 (Carga en <2 segundos).
    """
    cache_key = "agents_list_all"
    
    # ─── PATRÓN CACHE-ASIDE: FLUJO DE LECTURA ───
    
    # PASO 1: Intentar leer desde la caché (Memoria rápida)
    if redis_db is not None:
        try:
            cached_data = redis_db.get(cache_key)
            if cached_data:
                logger.info("Cache-Aside [HIT]: Lista de agentes obtenida de Redis")
                return {"agents": json.loads(cached_data)}
        except Exception:
            # Tolerancia a fallos: Fallback silencioso si Redis está caído
            pass

    # PASO 2: Cache Miss -> ir a la fuente de la verdad (PostgreSQL)
    logger.info("Cache-Aside [MISS]: Lista de agentes obtenida de PostgreSQL")
    agentes = listar_agentes()

    # PASO 3: Guardar en caché con tiempo de vida (TTL = 60 seg) para futuras peticiones
    if redis_db is not None:
        try:
            agentes_dict = [a.model_dump(mode="json") for a in agentes]
            redis_db.setex(cache_key, 60, json.dumps(agentes_dict))
        except Exception:
            pass

    return {
        "agents": agentes,
    }


@router.get("/delta")
def delta_sync(
    since: str,
    tenant_id: str | None = None,
):
    """RF23 CA-03/CA-04: devuelve solo agentes modificados desde `since` (ISO-8601).

    El cliente pasa su último timestamp de sync; el servidor responde con el
    delta (lista de agentes cambiados) y el nuevo `server_time` para la próxima
    consulta. Si no hubo cambios la lista viene vacía (zero-byte diff).

    CA-04: con SQLite local la consulta tarda < 1 ms para 100 agentes;
    la red 4G añade ~100-300 ms — muy por debajo del SLA de 5 s.
    """
    server_time = datetime.now(timezone.utc).isoformat()
    with get_session() as session:
        q = session.query(AgentDB).filter(AgentDB.updated_at > since)
        if tenant_id:
            q = q.filter(AgentDB.tenant_id == tenant_id)
        agentes = q.order_by(AgentDB.updated_at).all()

    return {
        "since": since,
        "server_time": server_time,
        "changes": len(agentes),
        "agents": [
            {
                "id": a.id,
                "nombre": a.nombre,
                "tipo": a.tipo,
                "estado": a.estado,
                "tenant_id": a.tenant_id,
                "owner": a.owner,
                "updated_at": a.updated_at,
            }
            for a in agentes
        ],
    }


@router.get("/{agent_id}")
def get_agent(agent_id: str):
    """
    Implementación del patrón Cache-Aside para lectura individual.
    Optimiza el acceso al Detalle del Agente (HU-21).
    """
    cache_key = f"agent_{agent_id}"

    # PATRÓN CACHE-ASIDE: PASO 1 (Leer Caché)
    if redis_db is not None:
        try:
            cached_data = redis_db.get(cache_key)
            if cached_data:
                logger.info(f"Cache-Aside [HIT]: Agente {agent_id}")
                return {"agent": json.loads(cached_data)}
        except Exception:
            pass

    # PATRÓN CACHE-ASIDE: PASO 2 (Cache Miss -> Origen)
    logger.info(f"Cache-Aside [MISS]: Agente {agent_id}")
    agent = obtener_agente_por_id(agent_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Agente no encontrado",
        )

    # PASO 3: Guardar en Caché
    if redis_db is not None:
        try:
            redis_db.setex(cache_key, 60, json.dumps(agent.model_dump(mode="json")))
        except Exception:
            pass

    return {
        "agent": agent,
    }


@router.patch("/{agent_id}/state")
def update_agent_state(agent_id: str, update_data: StateUpdate):
    with get_session() as session:
        agent = session.get(AgentDB, agent_id)

        if agent is None:
            raise HTTPException(
                status_code=404,
                detail="Agente no encontrado",
            )

        agent.estado = update_data.estado
        agent.updated_at = datetime.now(timezone.utc).isoformat()  # RF23 CA-03

        config = json.loads(agent.config_json)
        config["estado"] = update_data.estado
        agent.config_json = json.dumps(
            config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        session.commit()
        
        agent_actualizado = _a_schema(agent)

        # ─── PATRÓN CACHE-ASIDE: FLUJO DE ESCRITURA ───
        # PASO 4: Invalidar caché tras la escritura en BD para mantener la coherencia
        if redis_db is not None:
            try:
                redis_db.delete("agents_list_all")
                redis_db.delete(f"agent_{agent_id}")
                logger.info(f"Cache-Aside [INVALIDATE]: Caché limpiada tras actualización de estado")
            except Exception:
                pass

        return {
            "message": "Estado actualizado",
            "agent": agent_actualizado,
        }