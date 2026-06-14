"""Smoke de la API core unificada (wiki 6.2/6.3): un solo proceso sirve los
endpoints de todos los módulos, y los del Módulo 5 (RF17-RF20) degradan a
503 limpio cuando Neo4j no está configurado."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_rutas_de_todos_los_modulos_montadas_en_un_solo_app():
    paths = {r.path for r in app.routes}
    # Módulo 2 (Despliegue / CI-CD)
    assert "/api/v1/agents/{agent_id}/deploy" in paths
    assert "/api/v1/agents/{agent_id}/versions" in paths
    assert "/api/v1/agents/{agent_id}/deployments" in paths
    assert "/api/v1/notifications/" in paths
    # Módulos 1/3 (agents/templates/security)
    assert "/api/v1/agents/" in paths
    assert "/api/v1/templates/" in paths
    assert "/api/v1/security/reports" in paths
    # Módulo 4 (auth/tenants/governance; su audit vive en /security/logs)
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/tenants/" in paths
    assert "/api/v1/security/logs/" in paths
    # Módulo 5 (RF17-RF20) — antes solo existían en su app standalone (H1)
    assert "/api/v1/traces/recent" in paths
    assert "/api/v1/audit/verify/{tenant_id}" in paths
    assert "/api/v1/metrics/business" in paths
    assert "/api/v1/executions/{execution_id}/replay" in paths


def test_audit_del_modulo4_ya_no_colisiona_con_el_audit_trail():
    # H10: ambos compartían /api/v1/audit (GET / y POST /); el del Módulo 4
    # se movió a /api/v1/security/logs y /api/v1/audit quedó para RF18.
    paths = {r.path for r in app.routes}
    assert "/api/v1/security/logs/tenant/{tenant_id}" in paths
    assert "/api/v1/audit/export/json/{tenant_id}" in paths


def test_endpoints_modulo5_sin_neo4j_responden_503(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    urls = [
        "/api/v1/traces/recent",
        "/api/v1/audit/",
        "/api/v1/metrics/business",
        "/api/v1/executions/exec-demo/replay",
    ]
    for url in urls:
        respuesta = client.get(url)
        assert respuesta.status_code == 503, f"{url} -> {respuesta.status_code}"
        assert "Neo4j no configurado" in respuesta.json()["detail"]


def test_docs_y_openapi_cargan():
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
