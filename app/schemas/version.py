from pydantic import BaseModel


# Módulo 2 (Despliegue / CI-CD) — RF07: versionado inmutable.
# Mismo estilo snake_case que AgentConfig/TemplateConfig. La forma coincide con
# el tipo `Version` del frontend (src/types/Version.ts).
class Version(BaseModel):
    id: str
    numero: int
    fecha: str               # ISO-8601
    autor: str
    hash_sha256: str
    estado: str = "activa"   # "activa" | "inactiva" | "rollback"
    descripcion: str = ""
