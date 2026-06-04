from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from services.audit_chain_service import AuditChainService

router = APIRouter(
    prefix="/audit",
    tags=["RF18 - Audit Trail"]
)

service = AuditChainService()


class AuditEventRequest(BaseModel):
    agent_id: str
    tenant_id: str
    event_type: str
    input_data: str
    output_data: str
    policy_result: str
    user_id: str


@router.post("/")
def create_audit_event(event: AuditEventRequest):
    return service.create_audit_event(
        agent_id=event.agent_id,
        tenant_id=event.tenant_id,
        event_type=event.event_type,
        input_data=event.input_data,
        output_data=event.output_data,
        policy_result=event.policy_result,
        user_id=event.user_id
    )


@router.get("/")
def get_audit_events(
    tenant_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    policy_result: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None)
):
    return service.get_audit_events(
        tenant_id=tenant_id,
        agent_id=agent_id,
        event_type=event_type,
        policy_result=policy_result,
        start_date=start_date,
        end_date=end_date
    )


@router.get("/verify/{tenant_id}")
def verify_audit_chain(tenant_id: str):
    return service.verify_chain_integrity(tenant_id)


@router.get("/export/json/{tenant_id}")
def export_audit_json(tenant_id: str):
    return service.export_audit_json(tenant_id)


@router.get("/daily-check/{tenant_id}")
def daily_integrity_check_mock(tenant_id: str):
    return service.daily_integrity_check_mock(tenant_id)


@router.post("/setup/indexes")
def setup_audit_indexes():
    return service.create_indexes()


@router.put("/{audit_id}")
def update_audit_event_blocked(audit_id: str):
    raise HTTPException(
        status_code=403,
        detail="Audit trail is append-only. Audit events cannot be modified."
    )


@router.delete("/{audit_id}")
def delete_audit_event_blocked(audit_id: str):
    raise HTTPException(
        status_code=403,
        detail="Audit trail is append-only. Audit events cannot be deleted."
    )