from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers.agents import router as agents_router
from app.routers.templates import router as templates_router
from app.routers.security import router as security_router
# Módulo 2 (Despliegue / CI-CD) — RF05/RF06/RF07
from app.routers.deployments import router as deployments_router
from app.routers.versions import router as versions_router
from app.routers.environments import router as environments_router
from app.routers.autenticacion import router as auth_router
from app.routers.tenants import router as tenants_router
from app.routers.governance import router as governance_router
from app.routers.audit import router as audit_router

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
# Módulo 4 (Despliegue / CI-CD)
app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(governance_router)
app.include_router(audit_router)

@app.get("/")
def root():
    return {
        "message": "AgentWatch Backend funcionando"
    }

