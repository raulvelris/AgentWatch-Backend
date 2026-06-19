from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.routers.agents import router as agents_router
from app.routers.templates import router as templates_router
from app.routers.security import router as security_router
# Módulo 2 (Despliegue / CI-CD) — RF05/RF06/RF07
from app.routers.deployments import router as deployments_router
from app.routers.versions import router as versions_router
from app.routers.environments import router as environments_router
from app.routers.env_vars import router as env_vars_router
from app.routers.notifications import router as notifications_router
from app.routers.autenticacion import router as auth_router
from app.routers.tenants import router as tenants_router
from app.routers.governance import router as governance_router
from app.routers.audit import router as audit_router
# Módulo 5 (Trazabilidad, RF17-RF20) — API core unificada (wiki 6.2/6.3):
# los routers de rf17_rf20_gabriel se montan aquí; su main.py standalone
# queda deprecado. Sin NEO4J_URI responden 503 ("Neo4j no configurado").
from rf17_rf20_gabriel.routes.traces import router as traces_router
from rf17_rf20_gabriel.routes.audit import router as audit_trail_router
from rf17_rf20_gabriel.routes.metrics import router as metrics_router
from rf17_rf20_gabriel.routes.replay import router as replay_router

# Seed idempotente del Módulo 2: crea schema y triggers de inmutabilidad
# (RF07) si no existen. A nivel de import (y no en lifespan) para que el
# TestClient de los tests existentes —que no usa context manager— también
# tenga la BD lista.
init_db()

app = FastAPI(
    title="AgentWatch API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    # Orígenes desde settings (CORS_ORIGINS, separados por coma). Para acceso
    # desde celular en la misma red WiFi, agregar la IP local en .env
    # (ver .env.example); los defaults cubren localhost:5173/8081 y 127.0.0.1.
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router)
app.include_router(templates_router)
app.include_router(security_router)
# Módulo 2 (Despliegue / CI-CD)
app.include_router(deployments_router)
app.include_router(versions_router)
app.include_router(environments_router)
app.include_router(env_vars_router)
app.include_router(notifications_router)
# Módulo 4 (Despliegue / CI-CD)
app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(governance_router)
app.include_router(audit_router)
# Módulo 5 (Trazabilidad / Neo4j) — sus routers traen prefijos cortos
# (/traces, /audit, /metrics, /executions), igual que en su main standalone.
app.include_router(traces_router, prefix="/api/v1")
app.include_router(audit_trail_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(replay_router, prefix="/api/v1")

@app.get("/")
def root():
    return {
        "message": "AgentWatch Backend funcionando"
    }

