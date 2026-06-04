from fastapi import APIRouter
from pydantic import BaseModel
from services.trace_graph_service import TraceGraphService

router = APIRouter(
    prefix="/traces",
    tags=["RF17 - Neo4j Traces"]
)

service = TraceGraphService()


class TraceRequest(BaseModel):
    execution_id: str
    tenant_id: str
    agent_id: str


@router.post("/")
def create_trace(trace: TraceRequest):
    return service.create_execution_trace(
        trace.execution_id,
        trace.tenant_id,
        trace.agent_id
    )


@router.post("/setup/indexes")
def setup_indexes():
    return service.create_indexes()


@router.get("/recent")
def get_recent_traces():
    return service.get_recent_traces()


@router.get("/tenant/{tenant_id}")
def get_traces_by_tenant(tenant_id: str):
    return service.get_traces_by_tenant(tenant_id)


@router.get("/agent/{agent_id}")
def get_traces_by_agent(agent_id: str):
    return service.get_traces_by_agent(agent_id)


@router.get("/policy/{result_value}")
def get_policy_checks_by_result(result_value: str):
    return service.get_policy_checks_by_result(result_value)


@router.post("/archive/mock")
def archive_old_traces_mock():
    return service.mock_archive_old_traces()


@router.get("/{execution_id}")
def get_trace(execution_id: str):
    return service.get_execution_trace(execution_id)