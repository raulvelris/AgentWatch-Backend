from pydantic import BaseModel
from uuid import UUID


class AgentConfig(BaseModel):
    id: UUID
    nombre: str
    tipo: str
    proposito: str
    fuente: str
    descripcion_fuente: str
    regla: str
    supervision: str
    estado: str = "DRAFT"