from fastapi import APIRouter
from app.schemas.policy import Policy

router = APIRouter(
    prefix="/api/v1/governance",
    tags=["Governance"]
)

policies_db = []


@router.post("/policies")
def create_policy(policy: Policy):

    policies_db.append(policy)

    return {
        "message": "Política creada",
        "policy": policy
    }


@router.get("/policies")
def list_policies():

    return {
        "policies": policies_db
    }


@router.get("/tenant/{tenant_id}")
def get_tenant_policies(tenant_id: str):

    tenant_policies = [
        policy for policy in policies_db
        if policy.tenant_id == tenant_id
    ]

    return {
        "tenant": tenant_id,
        "policies": tenant_policies
    }

@router.get("/tenant/{tenant_id}/policies-vulnerable")
def get_policies_vulnerable(tenant_id: str):

    return {
        "tenant": tenant_id,
        "policies": policies_db
    }