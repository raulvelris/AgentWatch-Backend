import os
import json
import hashlib
from datetime import datetime, timezone

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class AuditChainService:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(
                os.getenv("NEO4J_USER"),
                os.getenv("NEO4J_PASSWORD")
            )
        )
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")

    def generate_sha256(self, value):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def get_last_audit_hash(self, session, tenant_id):
        query = """
        MATCH (a:AuditEvent {tenant_id:$tenant_id})
        RETURN a.current_hash AS current_hash
        ORDER BY a.sequence_number DESC
        LIMIT 1
        """
        record = session.run(query, tenant_id=tenant_id).single()
        return "GENESIS" if record is None else record["current_hash"]

    def get_next_sequence_number(self, session, tenant_id):
        query = """
        MATCH (a:AuditEvent {tenant_id:$tenant_id})
        RETURN count(a) AS total
        """
        record = session.run(query, tenant_id=tenant_id).single()
        return record["total"] + 1

    def create_audit_event(
        self,
        agent_id,
        tenant_id,
        event_type,
        input_data,
        output_data,
        policy_result,
        user_id
    ):
        timestamp = datetime.now(timezone.utc).isoformat()

        input_hash = self.generate_sha256(input_data)
        output_hash = self.generate_sha256(output_data)

        with self.driver.session(database=self.database) as session:
            previous_hash = self.get_last_audit_hash(session, tenant_id)
            sequence_number = self.get_next_sequence_number(session, tenant_id)

            payload = {
                "timestamp": timestamp,
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "event_type": event_type,
                "input_hash": input_hash,
                "output_hash": output_hash,
                "policy_result": policy_result,
                "user_id": user_id,
                "previous_hash": previous_hash,
                "sequence_number": sequence_number
            }

            current_hash = self.generate_sha256(
                json.dumps(payload, sort_keys=True)
            )

            query = """
            CREATE (a:AuditEvent {
                timestamp:$timestamp,
                agent_id:$agent_id,
                tenant_id:$tenant_id,
                event_type:$event_type,
                input_hash:$input_hash,
                output_hash:$output_hash,
                policy_result:$policy_result,
                user_id:$user_id,
                previous_hash:$previous_hash,
                current_hash:$current_hash,
                sequence_number:$sequence_number
            })
            RETURN a
            """

            session.run(
                query,
                timestamp=timestamp,
                agent_id=agent_id,
                tenant_id=tenant_id,
                event_type=event_type,
                input_hash=input_hash,
                output_hash=output_hash,
                policy_result=policy_result,
                user_id=user_id,
                previous_hash=previous_hash,
                current_hash=current_hash,
                sequence_number=sequence_number
            )

        return {
            "message": "Audit event created",
            "sequence_number": sequence_number,
            "previous_hash": previous_hash,
            "current_hash": current_hash,
            "input_hash": input_hash,
            "output_hash": output_hash
        }

    def get_audit_events(
        self,
        tenant_id=None,
        agent_id=None,
        event_type=None,
        policy_result=None,
        start_date=None,
        end_date=None
    ):
        query = """
        MATCH (a:AuditEvent)
        WHERE ($tenant_id IS NULL OR a.tenant_id = $tenant_id)
          AND ($agent_id IS NULL OR a.agent_id = $agent_id)
          AND ($event_type IS NULL OR a.event_type = $event_type)
          AND ($policy_result IS NULL OR a.policy_result = $policy_result)
          AND ($start_date IS NULL OR a.timestamp >= $start_date)
          AND ($end_date IS NULL OR a.timestamp <= $end_date)
        RETURN a
        ORDER BY a.sequence_number ASC
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(
                query,
                tenant_id=tenant_id,
                agent_id=agent_id,
                event_type=event_type,
                policy_result=policy_result,
                start_date=start_date,
                end_date=end_date
            )

            return [dict(record["a"]) for record in result]

    def verify_chain_integrity(self, tenant_id):
        query = """
        MATCH (a:AuditEvent {tenant_id:$tenant_id})
        RETURN a
        ORDER BY a.sequence_number ASC
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, tenant_id=tenant_id)
            events = [dict(record["a"]) for record in result]

        if len(events) == 0:
            return {
                "tenant_id": tenant_id,
                "valid": True,
                "message": "No audit events found",
                "events_checked": 0
            }

        previous_hash = "GENESIS"

        for event in events:
            payload = {
                "timestamp": event["timestamp"],
                "agent_id": event["agent_id"],
                "tenant_id": event["tenant_id"],
                "event_type": event["event_type"],
                "input_hash": event["input_hash"],
                "output_hash": event["output_hash"],
                "policy_result": event["policy_result"],
                "user_id": event["user_id"],
                "previous_hash": event["previous_hash"],
                "sequence_number": event["sequence_number"]
            }

            recalculated_hash = self.generate_sha256(
                json.dumps(payload, sort_keys=True)
            )

            if event["previous_hash"] != previous_hash:
                return {
                    "tenant_id": tenant_id,
                    "valid": False,
                    "message": "Hash chain broken: previous_hash does not match",
                    "failed_sequence": event["sequence_number"]
                }

            if event["current_hash"] != recalculated_hash:
                return {
                    "tenant_id": tenant_id,
                    "valid": False,
                    "message": "Hash chain broken: current_hash was altered",
                    "failed_sequence": event["sequence_number"]
                }

            previous_hash = event["current_hash"]

        return {
            "tenant_id": tenant_id,
            "valid": True,
            "message": "Audit chain integrity verified successfully",
            "events_checked": len(events)
        }

    def export_audit_json(self, tenant_id):
        events = self.get_audit_events(tenant_id=tenant_id)
        verification = self.verify_chain_integrity(tenant_id)

        return {
            "export_type": "JSON",
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "digital_signature_mock": self.generate_sha256(
                json.dumps(events, sort_keys=True)
            ),
            "integrity_verification": verification,
            "events": events
        }

    def daily_integrity_check_mock(self, tenant_id):
        verification = self.verify_chain_integrity(tenant_id)

        return {
            "message": "Simulación de verificación automática diaria",
            "tenant_id": tenant_id,
            "cron": "0 0 * * *",
            "result": verification
        }

    def create_indexes(self):
        queries = [
            """
            CREATE INDEX audit_tenant_index
            IF NOT EXISTS
            FOR (a:AuditEvent)
            ON (a.tenant_id)
            """,
            """
            CREATE INDEX audit_agent_index
            IF NOT EXISTS
            FOR (a:AuditEvent)
            ON (a.agent_id)
            """,
            """
            CREATE INDEX audit_event_type_index
            IF NOT EXISTS
            FOR (a:AuditEvent)
            ON (a.event_type)
            """,
            """
            CREATE INDEX audit_sequence_index
            IF NOT EXISTS
            FOR (a:AuditEvent)
            ON (a.sequence_number)
            """,
            """
            CREATE INDEX audit_timestamp_index
            IF NOT EXISTS
            FOR (a:AuditEvent)
            ON (a.timestamp)
            """
        ]

        with self.driver.session(database=self.database) as session:
            for query in queries:
                session.run(query)

        return {
            "message": "Audit indexes created correctly"
        }