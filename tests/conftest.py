"""Configuración compartida de tests del backend AgentWatch.

Fija una base de datos temporal ANTES de que cualquier test importe
app.main: así la suite nunca ensucia el ./agentwatch.db local y cada
corrida de pytest parte de un archivo limpio.
"""

import os
import tempfile

import pytest

_tmpdir = tempfile.mkdtemp(prefix="agentwatch-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + _tmpdir.replace("\\", "/") + "/test.db"


@pytest.fixture
def sin_sleep(monkeypatch):
    """Deploy sin los ~3s del pipeline simulado (5 fases x asyncio.sleep(0.6)).

    Compartida por toda la suite (antes vivía solo en test_governance_gate).
    El import es lazy para no importar la app antes de que DATABASE_URL quede
    fijada arriba."""
    from app.routers import deployments

    async def _sleep_instantaneo(_segundos):
        return None

    monkeypatch.setattr(deployments.asyncio, "sleep", _sleep_instantaneo)
