from fastapi import APIRouter, Header, HTTPException
from app.schemas.agent import AgentConfig, AgentCreate
from app.services.autenticacion_serv import obtener_datos_token

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Agents"]
)

agents_db = []


@router.post("/")
def create_agent(
    agent: AgentCreate,
    authorization: str = Header(default=None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Token requerido"
        )

    token = authorization.replace("Bearer ", "")
    datos = obtener_datos_token(token)

    nuevo_agente = AgentConfig(
        **agent.model_dump(),
        tenant_id=datos["tenant"],
        owner=datos["sub"]
    )

    agents_db.append(nuevo_agente)

    return {
        "message": "Agente creado correctamente",
        "agent": nuevo_agente
    }


@router.get("/")
def list_agents():
    return {
        "agents": agents_db
    }