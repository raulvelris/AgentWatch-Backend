from pydantic import BaseModel


# Módulo 2 (Despliegue / CI-CD) — RF06: ambientes y promotion controlada.
class PromoteRequest(BaseModel):
    ambiente_origen: str = "staging"
    ambiente_destino: str = "prod"
    solicitante: str
    # STUB de autorización: mientras el Módulo 4 (auth/RBAC, RF13) no exponga JWT,
    # el rol se recibe en el body. La promoción a prod exige rol "ADMIN".
    rol_solicitante: str = "DEVELOPER"
