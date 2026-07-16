import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@patch("app.routers.agents.redis_db")
def test_cache_aside_lectura(mock_redis):
    # Simulamos un Cache MISS (Redis no tiene el dato)
    mock_redis.get.return_value = None
    
    # Hacemos la petición
    resp = client.get("/api/v1/agents/")
    assert resp.status_code == 200
    
    # 1. Verificamos que se intentó leer la caché
    mock_redis.get.assert_called_once_with("agents_list_all")
    
    # 2. Verificamos que, al no estar en caché, se fue a BD y LUEGO se guardó en caché (setex)
    assert mock_redis.setex.called
    args, kwargs = mock_redis.setex.call_args
    assert args[0] == "agents_list_all"
    assert args[1] == 60  # El TTL que le pusimos

@patch("app.routers.agents.redis_db")
def test_cache_aside_invalidacion_escritura(mock_redis):
    # Creamos un agente para probar
    agente_fake = {
        "id": "11111111-2222-3333-4444-555555555555",
        "nombre": "Agente de Prueba Cache",
        "tipo": "Testing",
        "proposito": "Test",
        "fuente": "Test",
        "descripcion_fuente": "Test",
        "regla": "Test",
        "supervision": "Test",
        "estado": "ACTIVE",
        "tenant_id": "tenant_test",
        "owner": "admin_test"
    }
    client.post("/api/v1/agents/", json=agente_fake)
    
    # Ahora pausamos al agente (lo que haría tu app móvil)
    mock_redis.reset_mock()
    resp = client.patch(f"/api/v1/agents/{agente_fake['id']}/state", json={"estado": "PAUSED"})
    assert resp.status_code == 200
    
    # Verificamos que se haya invalidado la caché tras la escritura
    # Se debe haber llamado a delete("agents_list_all") y delete("agent_{id}")
    assert mock_redis.delete.call_count == 2
    mock_redis.delete.assert_any_call("agents_list_all")
    mock_redis.delete.assert_any_call(f"agent_{agente_fake['id']}")

@patch("app.routers.agents.redis_db")
def test_cache_aside_info_agente(mock_redis):
    # Simulamos el info de un agente (GET /agents/{id})
    # Reusamos el agente fake creado en el test anterior (o uno nuevo si es test aislado)
    # Cache MISS inicial
    mock_redis.get.return_value = None
    agent_id = "11111111-2222-3333-4444-555555555555"
    
    resp = client.get(f"/api/v1/agents/{agent_id}")
    if resp.status_code == 200:
        # Verificamos que se intentó leer la caché específica del agente
        mock_redis.get.assert_called_once_with(f"agent_{agent_id}")
        # Verificamos que se guardó en caché
        assert mock_redis.setex.called
        args, kwargs = mock_redis.setex.call_args
        assert args[0] == f"agent_{agent_id}"

@patch("app.routers.agents.redis_db")
def test_cache_aside_crear_agente(mock_redis):
    # Simulamos la creación de un agente nuevo
    nuevo_agente = {
        "id": "99999999-9999-9999-9999-999999999999",
        "nombre": "Agente Nuevo",
        "tipo": "Testing",
        "proposito": "Test",
        "fuente": "Test",
        "descripcion_fuente": "Test",
        "regla": "Test",
        "supervision": "Test",
        "estado": "ACTIVE",
        "tenant_id": "tenant_test",
        "owner": "admin_test"
    }
    
    resp = client.post("/api/v1/agents/", json=nuevo_agente)
    assert resp.status_code == 200
    
    # Al crear un agente, se debe invalidar la lista general
    mock_redis.delete.assert_called_with("agents_list_all")
