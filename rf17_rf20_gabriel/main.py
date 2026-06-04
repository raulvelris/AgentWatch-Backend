from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.traces import router as traces_router
from routes.audit import router as audit_router
from routes.metrics import router as metrics_router
from routes.replay import router as replay_router

app = FastAPI(
    title="AgentWatch Backend",
    description="""
    Backend RF17 RF18 RF19 RF20

    RF17 -> Neo4j Graph Traces
    RF18 -> Audit Trail Hash Chain
    RF19 -> Business Metrics ROI
    RF20 -> Execution Replay
    """,
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# RF17
app.include_router(
    traces_router,
    prefix="/api/v1"
)

# RF18
app.include_router(
    audit_router,
    prefix="/api/v1"
)

# RF19
app.include_router(
    metrics_router,
    prefix="/api/v1"
)

# RF20
app.include_router(
    replay_router,
    prefix="/api/v1"
)


@app.get("/")
def home():

    return {

        "message": "AgentWatch Backend OK",

        "modules": [

            "RF17 - Neo4j Graph Traces",

            "RF18 - Audit Trail Hash Chain",

            "RF19 - Business Metrics ROI",

            "RF20 - Execution Replay"

        ],

        "database": "Neo4j",

        "status": "running"

    }


@app.get("/health")
def health():

    return {

        "status": "healthy",

        "backend": "AgentWatch",

        "modules_loaded": [

            "RF17",
            "RF18",
            "RF19",
            "RF20"

        ]

    }