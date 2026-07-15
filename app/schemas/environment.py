from pydantic import BaseModel


# Módulo 2 (Despliegue / CI-CD) — RF06: ambientes y promotion controlada.
# El contrato son SOLO los ambientes: el solicitante y el rol salen de los
# claims del JWT (deps.require_authenticated), no del body. Los campos viejos
# `solicitante` y `rol_solicitante` quedaron deprecados y se eliminaron del
# schema; si un cliente viejo los manda, pydantic los descarta sin error.
class PromoteRequest(BaseModel):
    ambiente_origen: str = "staging"
    ambiente_destino: str = "prod"
