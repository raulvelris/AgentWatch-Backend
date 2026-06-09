from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        # IP local de la PC para acceso desde celular en la misma red WiFi
        # en cmd: ipconfig → Adaptador de LAN inalámbrica Wi-Fi:
        # Dirección IPv4. . . . . . . . . . . . . . : (la ip a usar:8081, 5173)
        "http://192.168.1.49:8081", # (reemplazar con tu ip)
        "http://192.168.1.49:5173", # (reemplazar con tu ip)
    ],
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

