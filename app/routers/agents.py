from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.schemas.agent import AgentConfig

class StateUpdate(BaseModel):
    estado: str

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Agents"]
)

import uuid

agents_db = [
    AgentConfig(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        nombre="Soporte Nivel 1",
        tipo="Customer Service",
        proposito="Atención de consultas básicas",
        fuente="Knowledge Base",
        descripcion_fuente="Docs internos",
        regla="No insultar",
        supervision="Human-in-the-loop",
        estado="ACTIVE"
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
        estado="PAUSED"
    )
]


@router.post("/")
def create_agent(agent: AgentConfig):
    agents_db.append(agent)

    return {
        "message": "Agente creado correctamente",
        "agent": agent
    }


@router.get("/")
def list_agents():
    return {
        "agents": agents_db
    }

