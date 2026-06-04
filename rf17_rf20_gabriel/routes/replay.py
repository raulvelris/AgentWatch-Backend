from fastapi import APIRouter

from services.execution_replay_service import ExecutionReplayService

router = APIRouter(
    prefix="/executions",
    tags=["RF20 - Execution Replay"]
)

service = ExecutionReplayService()


@router.get("/{execution_id}/replay")
def get_execution_replay(execution_id: str):
    return service.get_execution_replay(execution_id)


@router.get("/{execution_id}/replay/graph")
def get_replay_graph(execution_id: str):
    return service.get_replay_graph(execution_id)


@router.get("/{execution_id}/replay/verify-idempotency")
def verify_replay_idempotency(execution_id: str):
    return service.verify_idempotency(execution_id)