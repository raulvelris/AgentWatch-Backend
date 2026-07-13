import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import get_session
from app.models import AgentDB
from app.schemas.agent import AgentConfig


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


_crear_agentes_demo_si_no_existen()


@router.post("/")
def create_agent(agent: AgentConfig):
    with get_session() as session:
        if session.get(AgentDB, str(agent.id)) is not None:
            raise HTTPException(
                status_code=409,
                detail="Ya existe un agente con ese ID",
            )

        registro = _guardar_agent_config(agent)
        session.add(registro)
        session.commit()

        return {
            "message": "Agente creado correctamente",
            "agent": _a_schema(registro),
        }


@router.get("/")
def list_agents():
    return {
        "agents": listar_agentes(),
    }


@router.get("/{agent_id}")
def get_agent(agent_id: str):
    agent = obtener_agente_por_id(agent_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Agente no encontrado",
        )

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

        config = json.loads(agent.config_json)
        config["estado"] = update_data.estado
        agent.config_json = json.dumps(
            config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        session.commit()

        return {
            "message": "Estado actualizado",
            "agent": _a_schema(agent),
        }