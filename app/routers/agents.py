from fastapi import APIRouter
from app.schemas.agent import AgentConfig

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Agents"]
)

agents_db = []


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