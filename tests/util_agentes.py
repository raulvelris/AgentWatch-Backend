"""Helper compartido de la suite: el deploy (RF05) exige desde el commit
b4a3188 que el agente exista en la tabla `agents` (AgentDB), así que los
tests crean agentes reales vía POST /api/v1/agents/ en vez de usar ids
inventados.

El id DEBE ser un UUID: AgentConfig.id es uuid.UUID y el deploy reconstruye
el schema desde la BD (un id legible pasa el insert directo pero revienta
con ValidationError al deployar).
"""

import uuid

from fastapi.testclient import TestClient


def crear_agente(client: TestClient, nombre: str = "Agente de prueba M2") -> str:
    """Crea un agente real por la API y devuelve su id (str de un UUID4)."""
    agent_id = str(uuid.uuid4())
    r = client.post(
        "/api/v1/agents/",
        json={
            "id": agent_id,
            "nombre": nombre,
            "tipo": "Test",
            "proposito": "pruebas del modulo 2",
            "fuente": "tests",
            "descripcion_fuente": "suite pytest",
            "regla": "ninguna",
            "supervision": "ninguna",
            "estado": "ACTIVE",
        },
    )
    assert r.status_code == 200, r.text
    return agent_id
