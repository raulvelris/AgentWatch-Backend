from fastapi import APIRouter, HTTPException

from app.schemas.policy import Policy
from app.services import governance_service

# Gobernanza: políticas persistidas en SQLite (tabla `policies`) vía
# governance_service. Las de tipo "release_gate" las consulta el Módulo 2
# al promover a prod (ver environments.promote y plan-mlops-release-gate.md).
#
# Limitación conocida (documentada, decisión de alcance): estos endpoints no
# exigen autenticación — cualquiera puede crear una política. La superficie
# es del Módulo 4 (auth/RBAC); gatearla con ADMIN queda como trabajo suyo.
router = APIRouter(
    prefix="/api/v1/governance",
    tags=["Governance"]
)


@router.post("/policies")
def create_policy(policy: Policy):
    try:
        creada = governance_service.crear_politica(policy)
    except governance_service.PoliticaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except governance_service.PoliticaDuplicada as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "message": "Política creada",
        "policy": creada
    }


@router.get("/policies")
def list_policies():

    return {
        "policies": governance_service.listar_politicas()
    }


@router.get("/tenant/{tenant_id}")
def get_tenant_policies(tenant_id: str):

    return {
        "tenant": tenant_id,
        "policies": governance_service.listar_politicas(tenant_id=tenant_id)
    }

@router.get("/tenant/{tenant_id}/policies-vulnerable")
def get_policies_vulnerable(tenant_id: str):
    # Demo deliberada de pen-testing del Módulo 4 (patrón *-vulnerable, como
    # /login-vulnerable): NO filtra por tenant a propósito. Se conserva la
    # semántica de la versión en memoria, ahora leyendo de la BD. Ojo: con
    # políticas que ya son enforcement real, esto fuga configuración de
    # seguridad cross-tenant — es exactamente lo que la demo quiere mostrar.
    return {
        "tenant": tenant_id,
        "policies": governance_service.listar_politicas()
    }
