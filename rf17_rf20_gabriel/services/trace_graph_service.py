import os
import time
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class TraceGraphService:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(
                os.getenv("NEO4J_USER"),
                os.getenv("NEO4J_PASSWORD")
            )
        )
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")

    def create_indexes(self):
        queries = [
            """
            CREATE INDEX execution_id_index
            IF NOT EXISTS
            FOR (e:ExecutionStart)
            ON (e.execution_id)
            """,
            """
            CREATE INDEX tenant_id_index
            IF NOT EXISTS
            FOR (e:ExecutionStart)
            ON (e.tenant_id)
            """,
            """
            CREATE INDEX timestamp_index
            IF NOT EXISTS
            FOR (e:ExecutionStart)
            ON (e.timestamp)
            """
        ]

        with self.driver.session(database=self.database) as session:
            for query in queries:
                session.run(query)

        return {"message": "Índices creados correctamente"}

    def create_execution_trace(self, execution_id, tenant_id, agent_id):
        start_time = time.perf_counter()

        query = """
        CREATE
        (start:ExecutionStart {
            execution_id:$execution_id,
            tenant_id:$tenant_id,
            agent_id:$agent_id,
            timestamp:datetime()
        }),
        (llm:LLMCall {
            model:'GPT-4',
            timestamp:datetime()
        }),
        (tool:ToolCall {
            tool_name:'SearchTool',
            timestamp:datetime()
        }),
        (policy:PolicyCheck {
            result:'PASS',
            timestamp:datetime()
        }),
        (end:ExecutionEnd {
            status:'SUCCESS',
            timestamp:datetime()
        })

        CREATE (llm)-[:TRIGGERED_BY {timestamp:datetime()}]->(start)
        CREATE (tool)-[:LED_TO {timestamp:datetime()}]->(llm)
        CREATE (policy)-[:LED_TO {timestamp:datetime()}]->(tool)
        CREATE (end)-[:PRODUCED {timestamp:datetime()}]->(policy)
        """

        with self.driver.session(database=self.database) as session:
            session.run(
                query,
                execution_id=execution_id,
                tenant_id=tenant_id,
                agent_id=agent_id
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "message": "Trace created",
            "execution_id": execution_id,
            "write_time_ms": elapsed_ms,
            "target_pdf": "<200ms"
        }

    def get_execution_trace(self, execution_id):
        start_time = time.perf_counter()

        query = """
        MATCH (s:ExecutionStart {execution_id:$execution_id})
        OPTIONAL MATCH p=(s)-[:TRIGGERED_BY|LED_TO|PRODUCED*1..4]-()
        RETURN p
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, execution_id=execution_id)
            paths = [str(r["p"]) for r in result if r["p"] is not None]

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "execution_id": execution_id,
            "read_time_ms": elapsed_ms,
            "target_pdf": "<50ms",
            "trace": paths
        }

    def get_recent_traces(self):
        query = """
        MATCH (s:ExecutionStart)
        RETURN s.execution_id AS execution_id,
               s.tenant_id AS tenant_id,
               s.agent_id AS agent_id,
               s.timestamp AS timestamp
        ORDER BY s.timestamp DESC
        LIMIT 10
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query)
            return [dict(r) for r in result]

    def get_traces_by_tenant(self, tenant_id):
        query = """
        MATCH (s:ExecutionStart {tenant_id:$tenant_id})
        RETURN s.execution_id AS execution_id,
               s.agent_id AS agent_id,
               s.timestamp AS timestamp
        ORDER BY s.timestamp DESC
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, tenant_id=tenant_id)
            return [dict(r) for r in result]

    def get_traces_by_agent(self, agent_id):
        query = """
        MATCH (s:ExecutionStart {agent_id:$agent_id})
        RETURN s.execution_id AS execution_id,
               s.tenant_id AS tenant_id,
               s.timestamp AS timestamp
        ORDER BY s.timestamp DESC
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, agent_id=agent_id)
            return [dict(r) for r in result]

    def get_policy_checks_by_result(self, result_value):
        query = """
        MATCH (p:PolicyCheck {result:$result_value})
        RETURN p.result AS result,
               p.timestamp AS timestamp
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, result_value=result_value)
            return [dict(r) for r in result]

    def mock_archive_old_traces(self):
        query = """
        MATCH (s:ExecutionStart)
        WHERE s.timestamp < datetime() - duration({days:90})
        RETURN count(s) AS total_archivable
        """

        with self.driver.session(database=self.database) as session:
            record = session.run(query).single()

        return {
            "message": "Simulación de archivado Azure Blob Storage",
            "total_archivable": record["total_archivable"],
            "note": "En producción esto se ejecutaría con Azure Function y guardaría las trazas en Azure Blob Storage."
        }