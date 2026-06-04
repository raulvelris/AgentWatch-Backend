from pydantic import BaseModel

class AuditLog(BaseModel):
    id: str

    usuario: str
    rol: str

    tenant_id: str

    endpoint: str
    accion: str

    resultado: str

    fecha: str