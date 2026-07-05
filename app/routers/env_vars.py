"""RF06/ADR-02.6: variables de entorno por ambiente, cifradas con Fernet.

CRUD sobre la tabla `agent_env_vars`. La BD solo guarda ciphertext y la API
solo devuelve valores enmascarados (EC-02.5). El cifrado/enmascarado vive en
`app.services.cifrado_fernet` (stand-in local de Azure Key Vault, ADR-02.6),
único punto a reemplazar cuando exista la suscripción de Key Vault.

Comparte el prefijo `/api/v1/agents` con environments.py; las rutas no se
solapan (`/{agent_id}/environments/{env}/vars`). Reutiliza la lista AMBIENTES
de environments.py para no duplicar la fuente de verdad de ambientes válidos.

Limitación conocida (decisión de alcance, no descuido): el PUT y el DELETE no
exigen autenticación todavía. El front los llama sin token y el JWT del header
llega con RF13 (Módulo 4). Cerrarlos con ADMIN, como se hizo con el POST de
governance, queda pendiente para cuando el front envíe el token. Ver
`app.services.deps.require_admin` para la dependencia ya lista.
"""

from fastapi import APIRouter, Body, HTTPException

from app.core.database import get_session
from app.models import AgentEnvVarDB
from app.routers.environments import AMBIENTES
from app.services import reloj
from app.services.cifrado_fernet import (
    ErrorDescifrado,
    cifrar,
    descifrar,
    enmascarar,
)

router = APIRouter(prefix="/api/v1/agents", tags=["Deployment - Environments"])


def _validar_ambiente(env: str) -> None:
    if env not in AMBIENTES:
        raise HTTPException(status_code=400, detail=f"Ambiente inválido: {env}")


@router.get("/{agent_id}/environments/{env}/vars")
def listar_vars(agent_id: str, env: str):
    """Devuelve las variables del agente en `env` con valores ENMASCARADOS."""
    _validar_ambiente(env)
    with get_session() as session:
        filas = (
            session.query(AgentEnvVarDB)
            .filter(
                AgentEnvVarDB.agent_id == agent_id,
                AgentEnvVarDB.ambiente == env,
            )
            .all()
        )
        # Desciframos solo para enmascarar: el valor en claro nunca sale de aquí.
        # Si la clave no coincide con la usada al cifrar (ENVVARS_KEY cambió o se
        # perdió la efímera tras un reinicio), respondemos 503 en vez de un 500
        # crudo: es estado de configuración del server, no un error del request.
        try:
            vars_enmascaradas = {
                f.nombre: enmascarar(descifrar(f.valor_cifrado)) for f in filas
            }
        except ErrorDescifrado as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    return {"vars": vars_enmascaradas}


@router.put("/{agent_id}/environments/{env}/vars")
def guardar_vars(agent_id: str, env: str, payload: dict = Body(...)):
    """Upsert de variables CIFRADAS con Fernet. Sobrescribe la combinación
    (agent_id, ambiente, nombre) si ya existe."""
    _validar_ambiente(env)
    vars_in = payload.get("vars")
    if not isinstance(vars_in, dict):
        raise HTTPException(
            status_code=400, detail="El cuerpo debe incluir 'vars' como objeto"
        )

    ahora = reloj.ahora_utc().isoformat()
    with get_session() as session:
        for nombre, valor in vars_in.items():
            token = cifrar(str(valor))
            existente = (
                session.query(AgentEnvVarDB)
                .filter(
                    AgentEnvVarDB.agent_id == agent_id,
                    AgentEnvVarDB.ambiente == env,
                    AgentEnvVarDB.nombre == nombre,
                )
                .first()
            )
            if existente is not None:
                existente.valor_cifrado = token
                existente.fecha = ahora
            else:
                session.add(
                    AgentEnvVarDB(
                        agent_id=agent_id,
                        ambiente=env,
                        nombre=nombre,
                        valor_cifrado=token,
                        fecha=ahora,
                    )
                )
        session.commit()
    return {"ok": True, "guardadas": len(vars_in)}


@router.delete("/{agent_id}/environments/{env}/vars/{nombre}")
def eliminar_var(agent_id: str, env: str, nombre: str):
    """Elimina una variable específica del ambiente."""
    _validar_ambiente(env)
    with get_session() as session:
        fila = (
            session.query(AgentEnvVarDB)
            .filter(
                AgentEnvVarDB.agent_id == agent_id,
                AgentEnvVarDB.ambiente == env,
                AgentEnvVarDB.nombre == nombre,
            )
            .first()
        )
        if fila is None:
            raise HTTPException(status_code=404, detail="Variable no encontrada")
        session.delete(fila)
        session.commit()
    return {"ok": True}
