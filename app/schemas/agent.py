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
    # Defaults provisionales: los datos demo de agents.py y el front actual
    # (WizardAgente) todavía no envían estos campos; sin default la app no
    # importa (ValidationError al construir agents_db) y POST /agents/ da 422.
    tenant_id: str = "tenant_a"
    owner: str = "admin_a"