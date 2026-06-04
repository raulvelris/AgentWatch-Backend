import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class BusinessMetricsService:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(
                os.getenv("NEO4J_USER"),
                os.getenv("NEO4J_PASSWORD")
            )
        )
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")

        self.default_config = {
            "tenant_id": "TEN001",
            "employee_hour_cost_usd": 8.0,
            "value_per_completed_task_usd": 15.0,
            "human_minutes_per_task": 30,
            "operation_cost_per_task_usd": 2.5
        }

    def get_config(self, tenant_id):
        return {
            "message": "Configuración de métricas obtenida correctamente",
            "config": {
                **self.default_config,
                "tenant_id": tenant_id
            }
        }

    def update_config(
        self,
        tenant_id,
        employee_hour_cost_usd,
        value_per_completed_task_usd,
        human_minutes_per_task,
        operation_cost_per_task_usd
    ):
        self.default_config = {
            "tenant_id": tenant_id,
            "employee_hour_cost_usd": employee_hour_cost_usd,
            "value_per_completed_task_usd": value_per_completed_task_usd,
            "human_minutes_per_task": human_minutes_per_task,
            "operation_cost_per_task_usd": operation_cost_per_task_usd
        }

        return {
            "message": "Configuración de métricas actualizada correctamente",
            "config": self.default_config
        }

    def get_business_metrics(
        self,
        tenant_id,
        agent_id=None,
        period="month"
    ):
        query = """
        MATCH (s:ExecutionStart)
        WHERE s.tenant_id = $tenant_id
          AND ($agent_id IS NULL OR s.agent_id = $agent_id)
        OPTIONAL MATCH (s)-[*1..4]-(e:ExecutionEnd)
        RETURN s.agent_id AS agent_id,
               count(DISTINCT s) AS total_tasks,
               count(DISTINCT e) AS completed_tasks
        ORDER BY agent_id
        """

        config = {
            **self.default_config,
            "tenant_id": tenant_id
        }

        with self.driver.session(database=self.database) as session:
            result = session.run(
                query,
                tenant_id=tenant_id,
                agent_id=agent_id
            )

            agents = []

            for record in result:
                total_tasks = record["total_tasks"] or 0
                completed_tasks = record["completed_tasks"] or 0

                operation_cost = total_tasks * config["operation_cost_per_task_usd"]
                generated_value = completed_tasks * config["value_per_completed_task_usd"]
                saved_hours = (completed_tasks * config["human_minutes_per_task"]) / 60

                roi = 0
                if operation_cost > 0:
                    roi = generated_value / operation_cost

                cost_per_task = 0
                if completed_tasks > 0:
                    cost_per_task = operation_cost / completed_tasks

                quality_rate = 0
                if total_tasks > 0:
                    quality_rate = (completed_tasks / total_tasks) * 100

                agents.append({
                    "agent_id": record["agent_id"],
                    "period": period,
                    "total_tasks": total_tasks,
                    "completed_tasks": completed_tasks,
                    "generated_value_usd": round(generated_value, 2),
                    "operation_cost_usd": round(operation_cost, 2),
                    "roi": round(roi, 2),
                    "cost_per_completed_task_usd": round(cost_per_task, 2),
                    "human_hours_saved": round(saved_hours, 2),
                    "quality_rate_percent": round(quality_rate, 2),
                    "calculation_detail": {
                        "roi_formula": "generated_value_usd / operation_cost_usd",
                        "generated_value_formula": "completed_tasks * value_per_completed_task_usd",
                        "operation_cost_formula": "total_tasks * operation_cost_per_task_usd",
                        "saved_hours_formula": "completed_tasks * human_minutes_per_task / 60"
                    }
                })

        return {
            "tenant_id": tenant_id,
            "agent_filter": agent_id,
            "period": period,
            "refresh_interval_ms": 300000,
            "config_used": config,
            "agents": agents
        }