from typing import Literal

from pydantic import BaseModel

class Policy(BaseModel):
    id: str
    tenant_id: str

    nombre: str
    descripcion: str

    severidad: str
    activa: bool = True

    # Release gate (MLOps): con tipo="release_gate", la política bloquea la
    # promoción a prod si la métrica no supera el umbral. Los defaults
    # replican el comportamiento previo: una política "informativa" no
    # bloquea nada y los requests existentes siguen validando sin cambios.
    # Literal y no str: un typo ("release-gate") crearía una política que el
    # gate nunca consulta — bypass silencioso; mejor 422 al crearla.
    tipo: Literal["informativa", "release_gate"] = "informativa"
    metrica: str | None = None  # soportada: "tasa_exito_despliegues"
    umbral: float | None = None  # tasa mínima exigida, en [0, 1]
    ventana: int | None = None  # últimos N despliegues (default 5 al evaluar)
