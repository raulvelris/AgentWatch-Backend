"""Gobernanza: persistencia de políticas y release gate de calidad (MLOps).

Conecta el módulo de Gobernanza con el Módulo 2 (Despliegue / CI-CD): una
política `tipo="release_gate"` activa bloquea la promoción a prod — incluso
para un ADMIN — si la tasa de éxito de los últimos N despliegues del agente
(`DeploymentRecordDB`, ya poblada por RF05) queda por debajo del umbral.

Diseño fail-open deliberado (ver docs/plan-mlops-release-gate.md):
- sin políticas de gate activas para el tenant → la promoción no se toca;
- agente sin historial de despliegues → la métrica no existe, no se reprueba.

Limitación conocida: las tablas del Módulo 2 no llevan `tenant_id`; el
agente se asume del tenant del solicitante (claim `tenant` del JWT, o
"tenant_a" sin token — mismo default que AgentConfig.tenant_id).
"""

from sqlalchemy.exc import IntegrityError

from app.core.database import get_session
from app.models import DeploymentRecordDB, PolicyDB
from app.schemas.policy import Policy

# Única métrica soportada por el gate hoy; ampliar aquí (y en la validación)
# si se agregan métricas nuevas.
METRICAS_SOPORTADAS = {"tasa_exito_despliegues"}
VENTANA_DEFAULT = 5


class PoliticaInvalida(ValueError):
    """Política release_gate malformada (métrica/umbral/ventana). El router
    la traduce a 422: mejor rechazar al configurar que fallar al promover."""


class PoliticaDuplicada(Exception):
    """Ya existe una política con ese id (el id lo elige el cliente)."""


def _a_dict(p: PolicyDB) -> dict:
    # Mismas claves que el schema Policy: la forma de respuesta del router
    # de gobernanza no cambia respecto a la versión en memoria.
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "nombre": p.nombre,
        "descripcion": p.descripcion,
        "severidad": p.severidad,
        "activa": p.activa,
        "tipo": p.tipo,
        "metrica": p.metrica,
        "umbral": p.umbral,
        "ventana": p.ventana,
    }


def _validar_release_gate(policy: Policy) -> None:
    """Valida la configuración de un gate ANTES de persistirla: una política
    con umbral=None evaluada en caliente daría TypeError en pleno promote."""
    if policy.metrica not in METRICAS_SOPORTADAS:
        raise PoliticaInvalida(
            f"Métrica no soportada para release_gate: {policy.metrica!r}; "
            f"usar una de: {sorted(METRICAS_SOPORTADAS)}"
        )
    if policy.umbral is None or not (0.0 <= policy.umbral <= 1.0):
        raise PoliticaInvalida(
            "release_gate requiere `umbral` en [0, 1] (tasa mínima de éxito)"
        )
    if policy.ventana is not None and policy.ventana < 1:
        raise PoliticaInvalida("`ventana` debe ser >= 1 (últimos N despliegues)")


def crear_politica(policy: Policy) -> dict:
    """Persiste una política (INSERT en `policies`). Valida los campos del
    gate al crear (fail-fast) y rechaza ids duplicados."""
    if policy.tipo == "release_gate":
        _validar_release_gate(policy)
    with get_session() as session:
        if session.get(PolicyDB, policy.id) is not None:
            raise PoliticaDuplicada(f"Ya existe una política con id {policy.id!r}")
        registro = PolicyDB(**policy.model_dump())
        session.add(registro)
        try:
            session.commit()
        except IntegrityError:
            # Dos requests concurrentes con el mismo id pueden pasar ambos el
            # session.get() de arriba (threadpool de FastAPI); el perdedor
            # choca contra la PK al hacer commit y también merece 409, no 500.
            session.rollback()
            raise PoliticaDuplicada(f"Ya existe una política con id {policy.id!r}")
        return _a_dict(registro)


def listar_politicas(tenant_id: str | None = None) -> list[dict]:
    """Todas las políticas, opcionalmente filtradas por tenant."""
    with get_session() as session:
        query = session.query(PolicyDB)
        if tenant_id is not None:
            query = query.filter(PolicyDB.tenant_id == tenant_id)
        return [_a_dict(p) for p in query.order_by(PolicyDB.id).all()]


def calcular_tasa_exito(agent_id: str, ventana: int) -> float | None:
    """Tasa de éxito de los últimos `ventana` despliegues del agente.

    None si el agente no tiene despliegues: "sin datos" no es lo mismo que
    0.0 — una métrica que no existe no se puede reprobar. Orden por `id`
    desc (autoincrement, monotónico) y no por `fecha` (string ISO)."""
    with get_session() as session:
        ultimos = (
            session.query(DeploymentRecordDB)
            .filter(DeploymentRecordDB.agent_id == agent_id)
            .order_by(DeploymentRecordDB.id.desc())
            .limit(ventana)
            .all()
        )
        if not ultimos:
            return None
        exitosos = sum(1 for d in ultimos if d.resultado == "success")
        return exitosos / len(ultimos)


def evaluar_gate_promocion(tenant_id: str, agent_id: str) -> tuple[bool, str]:
    """Release gate: evalúa las políticas `release_gate` activas del tenant
    contra el historial de despliegues del agente.

    Devuelve (aprobado, motivo). El bloqueo es duro: environments.promote()
    lo aplica también a un ADMIN (409, no 403: la identidad es válida, lo
    que falla es el estado de calidad del agente)."""
    with get_session() as session:
        # Se materializan los campos dentro del `with` (mismo patrón que
        # _a_dict / _a_schema en los routers): nada del ORM sale de la sesión.
        politicas = [
            _a_dict(p)
            for p in session.query(PolicyDB)
            .filter(
                PolicyDB.tenant_id == tenant_id,
                PolicyDB.tipo == "release_gate",
                PolicyDB.activa.is_(True),
            )
            .order_by(PolicyDB.id)
            .all()
        ]

    if not politicas:
        return True, "Sin políticas de gate activas"

    for politica in politicas:
        # Skip defensivo: crear_politica() valida, pero una fila insertada
        # por fuera de la API no debe tumbar el promote con un 500.
        if politica["metrica"] != "tasa_exito_despliegues" or politica["umbral"] is None:
            continue
        ventana = politica["ventana"] or VENTANA_DEFAULT
        tasa = calcular_tasa_exito(agent_id, ventana)
        if tasa is None:
            # Sin historial de despliegues no hay métrica que reprobar
            # (decisión abierta #2 del plan: permitir por defecto).
            continue
        if tasa < politica["umbral"]:
            return False, (
                f"Política '{politica['nombre']}' no superada: tasa de éxito "
                f"{tasa:.0%} < umbral requerido {politica['umbral']:.0%} "
                f"(últimos {ventana} despliegues)"
            )

    return True, "Todas las políticas de gate superadas"
