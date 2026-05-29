from pydantic import BaseModel


class TemplateConfig(BaseModel):
    id: str
    nombre: str
    descripcion: str
    caso_uso: str
    tiempo_estimado: str
    categoria: str
    favorito: bool = False