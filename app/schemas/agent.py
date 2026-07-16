from pydantic import BaseModel
from uuid import UUID


class AgentCreate(BaseModel):
    id: UUID
    nombre: str
    tipo: str
    proposito: str
    fuente: str
    descripcion_fuente: str
    regla: str
    supervision: str
    estado: str = "DRAFT"


class AgentConfig(AgentCreate):
    tenant_id: str
    owner: str