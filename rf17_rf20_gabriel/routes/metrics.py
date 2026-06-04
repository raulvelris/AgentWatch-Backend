from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.business_metrics_service import BusinessMetricsService

router = APIRouter(
    prefix="/metrics",
    tags=["RF19 - Business Metrics ROI"]
)

service = BusinessMetricsService()


class MetricsConfigRequest(BaseModel):
    tenant_id: str
    employee_hour_cost_usd: float
    value_per_completed_task_usd: float
    human_minutes_per_task: int
    operation_cost_per_task_usd: float


@router.get("/business")
def get_business_metrics(
    tenant_id: str = Query(default="TEN001"),
    agent_id: str | None = Query(default=None),
    period: str = Query(default="month")
):
    return service.get_business_metrics(
        tenant_id=tenant_id,
        agent_id=agent_id,
        period=period
    )


@router.get("/business/config")
def get_metrics_config(
    tenant_id: str = Query(default="TEN001")
):
    return service.get_config(tenant_id)


@router.post("/business/config")
def update_metrics_config(config: MetricsConfigRequest):
    return service.update_config(
        tenant_id=config.tenant_id,
        employee_hour_cost_usd=config.employee_hour_cost_usd,
        value_per_completed_task_usd=config.value_per_completed_task_usd,
        human_minutes_per_task=config.human_minutes_per_task,
        operation_cost_per_task_usd=config.operation_cost_per_task_usd
    )