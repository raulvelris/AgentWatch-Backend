from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.agents import router as agents_router
from app.routers.templates import router as templates_router
from app.routers.security import router as security_router
# Módulo 2 (Despliegue / CI-CD) — RF05/RF06/RF07
from app.routers.deployments import router as deployments_router
from app.routers.versions import router as versions_router
from app.routers.environments import router as environments_router

app = FastAPI(
    title="AgentWatch API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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


@app.get("/")
def root():
    return {
        "message": "AgentWatch Backend funcionando"
    }