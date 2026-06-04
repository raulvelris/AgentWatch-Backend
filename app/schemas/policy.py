from pydantic import BaseModel

class Policy(BaseModel):
    id: str
    tenant_id: str

    nombre: str
    descripcion: str

    severidad: str
    activa: bool = True