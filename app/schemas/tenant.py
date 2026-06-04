from pydantic import BaseModel
from typing import List

class Tenant(BaseModel):
    id: str
    nombre: str
    descripcion: str
    sector: str
    estado: str = "ACTIVO"

    usuarios: List[str] = []
    agentes: List[str] = []
    politicas: List[str] = []