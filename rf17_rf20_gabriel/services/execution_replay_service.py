import os
import time
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class ExecutionReplayService:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(
                os.getenv("NEO4J_USER"),
                os.getenv("NEO4J_PASSWORD")
            )
        )
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")

    def get_execution_replay(self, execution_id):
        start_time = time.perf_counter()

        query = """
        MATCH (s:ExecutionStart {execution_id:$execution_id})
        OPTIONAL MATCH (llm:LLMCall)-[:TRIGGERED_BY]->(s)
        OPTIONAL MATCH (tool:ToolCall)-[:LED_TO]->(llm)
        OPTIONAL MATCH (policy:PolicyCheck)-[:LED_TO]->(tool)
        OPTIONAL MATCH (end:ExecutionEnd)-[:PRODUCED]->(policy)
        RETURN s, llm, tool, policy, end
        LIMIT 1
        """

        with self.driver.session(database=self.database) as session:
            record = session.run(
                query,
                execution_id=execution_id
            ).single()

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if record is None:
            return {
                "execution_id": execution_id,
                "found": False,
                "message": "Execution not found",
                "load_time_ms": elapsed_ms,
                "target_pdf": "<2000ms",
                "steps": []
            }

        steps = []

        if record["s"]:
            steps.append({
                "step_number": 1,
                "step_type": "ExecutionStart",
                "title": "Inicio de ejecución",
                "description": "Se inicia la ejecución del agente.",
                "input": {
                    "execution_id": record["s"].get("execution_id"),
                    "tenant_id": record["s"].get("tenant_id"),
                    "agent_id": record["s"].get("agent_id")
                },
                "output": "Ejecución registrada correctamente",
                "policy_result": None,
                "tool_used": None,
                "status": "STARTED"
            })

        if record["llm"]:
            steps.append({
                "step_number": 2,
                "step_type": "LLMCall",
                "title": "Llamada al modelo LLM",
                "description": "El agente realiza una llamada al modelo de lenguaje.",
                "input": "Solicitud enviada al modelo",
                "output": f"Respuesta generada por {record['llm'].get('model', 'LLM')}",
                "policy_result": None,
                "tool_used": None,
                "status": "COMPLETED"
            })

        if record["tool"]:
            steps.append({
                "step_number": 3,
                "step_type": "ToolCall",
                "title": "Uso de herramienta",
                "description": "El agente utiliza una herramienta durante la ejecución.",
                "input": "Necesidad de búsqueda o consulta externa",
                "output": "Resultado obtenido desde herramienta",
                "policy_result": None,
                "tool_used": record["tool"].get("tool_name"),
                "status": "COMPLETED"
            })

        if record["policy"]:
            steps.append({
                "step_number": 4,
                "step_type": "PolicyCheck",
                "title": "Validación de políticas",
                "description": "Se verifica si la ejecución cumple las políticas definidas.",
                "input": "Resultado generado por el agente",
                "output": "Política evaluada correctamente",
                "policy_result": record["policy"].get("result"),
                "tool_used": None,
                "status": "COMPLETED"
            })

        if record["end"]:
            steps.append({
                "step_number": 5,
                "step_type": "ExecutionEnd",
                "title": "Fin de ejecución",
                "description": "La ejecución finaliza y se registra el estado final.",
                "input": "Ejecución procesada",
                "output": "Resultado final registrado",
                "policy_result": None,
                "tool_used": None,
                "status": record["end"].get("status")
            })

        return {
            "execution_id": execution_id,
            "found": True,
            "load_time_ms": elapsed_ms,
            "target_pdf": "<2000ms",
            "total_steps": len(steps),
            "replay_mode": "step-by-step",
            "controls_supported": [
                "play",
                "pause",
                "step-forward",
                "step-backward"
            ],
            "steps": steps
        }

    def get_replay_graph(self, execution_id):
        query = """
        MATCH p=(s:ExecutionStart {execution_id:$execution_id})-[*1..4]-()
        RETURN p
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(
                query,
                execution_id=execution_id
            )

            paths = [str(record["p"]) for record in result]

        return {
            "execution_id": execution_id,
            "graph_type": "Neo4j execution trace graph",
            "paths": paths,
            "message": "Graph data retrieved for replay visualization"
        }

    def verify_idempotency(self, execution_id):
        first_replay = self.get_execution_replay(execution_id)
        second_replay = self.get_execution_replay(execution_id)

        is_idempotent = first_replay["steps"] == second_replay["steps"]

        return {
            "execution_id": execution_id,
            "idempotent": is_idempotent,
            "message": (
                "Replay is idempotent"
                if is_idempotent
                else "Replay changed between executions"
            ),
            "first_total_steps": first_replay.get("total_steps", 0),
            "second_total_steps": second_replay.get("total_steps", 0)
        }