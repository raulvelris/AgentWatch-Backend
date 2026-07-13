from fastapi import APIRouter
from fastapi import HTTPException
from app.schemas.tenant import Tenant
from app.routers.agents import listar_agentes
from app.services.autenticacion_serv import obtener_datos_token

router = APIRouter(
    prefix="/api/v1/tenants",
    tags=["Tenants"]
)

tenants_db = []


@router.post("/")
def create_tenant(tenant: Tenant):
    tenants_db.append(tenant)

    return {
        "message": "Tenant creado correctamente",
        "tenant": tenant
    }


@router.get("/")
def list_tenants():
    return {
        "tenants": tenants_db
    }


@router.get("/{tenant_id}")
def get_tenant(tenant_id: str):

    tenant = next(
        (t for t in tenants_db if t.id == tenant_id),
        None
    )

    if not tenant:
        return {
            "error": "Tenant no encontrado"
        }

    return tenant


@router.get("/{tenant_id}/agents")
def get_tenant_agents(tenant_id: str):
    agentes = listar_agentes()

    tenant_agents = [
        agent for agent in agentes
        if agent.tenant_id == tenant_id
    ]

    return {
        "tenant": tenant_id,
        "agents": tenant_agents,
    }
#vulnerabilidad
@router.get("/{tenant_id}/agents-vulnerable")
def get_tenant_agents_vulnerable(tenant_id: str):
    return {
        "tenant": tenant_id,
        "agents": listar_agentes(),
    }

#vulnerabilidad
@router.get("/tenant-access-vulnerable/{tenant_id}")
def tenant_access_vulnerable(
    tenant_id: str,
    token: str
):

    datos = obtener_datos_token(token)

    return {
        "usuario": datos["sub"],
        "tenant_token": datos["tenant"],
        "tenant_solicitado": tenant_id,
        "acceso": "PERMITIDO"
    }

@router.get("/tenant-access-secure/{tenant_id}")
def tenant_access_secure(
    tenant_id: str,
    token: str
):

    datos = obtener_datos_token(token)

    if datos["tenant"] != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Cross-Tenant Access Bloqueado"
        )

    return {
        "usuario": datos["sub"],
        "tenant": tenant_id,
        "acceso": "PERMITIDO"
    }