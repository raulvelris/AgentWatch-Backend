"""Configuración compartida de tests del backend AgentWatch.

Fija una base de datos temporal ANTES de que cualquier test importe
app.main: así la suite nunca ensucia el ./agentwatch.db local y cada
corrida de pytest parte de un archivo limpio.
"""

import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="agentwatch-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + _tmpdir.replace("\\", "/") + "/test.db"
