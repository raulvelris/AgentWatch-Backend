"""Release gate de calidad (Gobernanza + Módulo 2, ver
docs/plan-mlops-release-gate.md): la promoción a prod consulta las políticas
`release_gate` activas del tenant y bloquea con 409 — incluso a un ADMIN —
si la tasa de éxito de los últimos N despliegues no supera el umbral.

Convenciones de siembra de historial (rapidez de la suite):
- despliegues fallidos: `?fallo=queued` (falla en la 1.ª fase → cero sleeps);
- despliegues exitosos: monkeypatch de asyncio.sleep del pipeline (no-op).
"""

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_session
from app.main import app
from app.models import PolicyDB
from tests.util_agentes import crear_agente

client = TestClient(app)


@pytest.fixture(autouse=True)
def limpiar_politicas():
    """Las políticas son configuración viva por tenant (no por agente): una
    creada en un test bloquearía los promote de los siguientes. Tabla limpia
    antes de cada test, y también al salir para no filtrar gates activos a
    los otros archivos de la suite (compatibilidad con los tests previos)."""

    def _vaciar():
        with get_session() as session:
            session.query(PolicyDB).delete()
            session.commit()

    _vaciar()
    yield
    _vaciar()


# La fixture `sin_sleep` (deploy sin esperas) ahora vive en conftest.py,
# compartida por toda la suite.


def _headers_admin(usuario: str = "admin_a") -> dict:
    """Token ADMIN vía el login stub del Módulo 4, en el header Authorization.
    Crear políticas ahora exige rol ADMIN (require_admin en governance.py)."""
    token = client.get("/api/v1/auth/login", params={"usuario": usuario}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _crear_politica(policy_id: str, tenant_id: str = "tenant_a", **extra) -> dict:
    base = {
        "id": policy_id,
        "tenant_id": tenant_id,
        "nombre": f"Gate {policy_id}",
        "descripcion": "tasa de éxito mínima para promover a prod",
        "severidad": "alta",
        "tipo": "release_gate",
        "metrica": "tasa_exito_despliegues",
        "umbral": 0.8,
        "ventana": 5,
    }
    base.update(extra)
    respuesta = client.post(
        "/api/v1/governance/policies", json=base, headers=_headers_admin()
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["policy"]


def _promover_a_prod_como_admin(agente: str):
    return client.post(
        f"/api/v1/agents/{agente}/promote",
        headers=_headers_admin(),
        json={
            "ambiente_origen": "staging",
            "ambiente_destino": "prod",
            "solicitante": "admin1",
            "rol_solicitante": "ADMIN",
        },
    )


def _sembrar_fallos(agente: str, cantidad: int):
    for _ in range(cantidad):
        r = client.post(
            f"/api/v1/agents/{agente}/deploy?fallo=queued", headers=_headers_admin()
        )
        assert r.status_code == 200


def _sembrar_exitos(agente: str, cantidad: int):
    for _ in range(cantidad):
        r = client.post(f"/api/v1/agents/{agente}/deploy", headers=_headers_admin())
        assert r.status_code == 200


def test_sin_politicas_de_gate_el_promote_no_cambia():
    # (a) Regresión: sin políticas release_gate, flujo idéntico al actual
    # (403 sin ADMIN, 200 aprobada con ADMIN) aunque el agente tenga fallos.
    agente = crear_agente(client)
    _sembrar_fallos(agente, 3)

    r = client.post(
        f"/api/v1/agents/{agente}/promote",
        headers=_headers_admin("viewer_a"),
        json={"ambiente_destino": "prod", "solicitante": "dev1", "rol_solicitante": "DEVELOPER"},
    )
    assert r.status_code == 403

    r = _promover_a_prod_como_admin(agente)
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "aprobada"


def test_promote_bloqueada_por_gate_aunque_sea_admin():
    # (b) Bloqueo duro: tasa 0% < umbral 80% → 409 incluso para ADMIN, con
    # el nombre de la política y las tasas en el detalle.
    agente = crear_agente(client)
    _crear_politica("pol-bloquea-admin")
    _sembrar_fallos(agente, 3)

    r = _promover_a_prod_como_admin(agente)
    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert "pol-bloquea-admin" in detalle
    assert "0%" in detalle and "80%" in detalle


def test_promote_pasa_cuando_la_tasa_supera_el_umbral(sin_sleep):
    # (c) Desbloqueo: éxitos recientes suben la tasa dentro de la ventana
    # (5 éxitos tras 2 fallos → últimos 5 = 100%) y la promoción pasa.
    agente = crear_agente(client)
    _crear_politica("pol-se-desbloquea")
    _sembrar_fallos(agente, 2)
    assert _promover_a_prod_como_admin(agente).status_code == 409

    _sembrar_exitos(agente, 5)
    r = _promover_a_prod_como_admin(agente)
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "aprobada"


def test_agente_sin_historial_no_se_bloquea():
    # (d) Sin despliegues previos no hay métrica que reprobar: pasa.
    _crear_politica("pol-sin-historial")
    r = _promover_a_prod_como_admin("gate-agente-virgen")
    assert r.status_code == 200


def test_politica_inactiva_no_bloquea():
    # (e) activa=False → la política no participa del gate.
    agente = crear_agente(client)
    _crear_politica("pol-inactiva", activa=False)
    _sembrar_fallos(agente, 3)
    r = _promover_a_prod_como_admin(agente)
    assert r.status_code == 200


def test_politica_de_otro_tenant_no_afecta():
    # (f) Aislamiento multi-tenant vía claim `tenant` del JWT: la política de
    # tenant_b no bloquea a admin_a (tenant_a); la de tenant_a sí.
    agente = crear_agente(client)
    _crear_politica("pol-tenant-b", tenant_id="tenant_b")
    _sembrar_fallos(agente, 3)

    token_a = client.get("/api/v1/auth/login", params={"usuario": "admin_a"}).json()["token"]
    encabezados = {"Authorization": f"Bearer {token_a}"}
    cuerpo = {
        "ambiente_origen": "staging",
        "ambiente_destino": "prod",
        "solicitante": "admin_a",
        "rol_solicitante": "ADMIN",
    }

    r = client.post(f"/api/v1/agents/{agente}/promote", headers=encabezados, json=cuerpo)
    assert r.status_code == 200  # la política de tenant_b no aplica

    _crear_politica("pol-tenant-a", tenant_id="tenant_a")
    r = client.post(f"/api/v1/agents/{agente}/promote", headers=encabezados, json=cuerpo)
    assert r.status_code == 409  # la de su propio tenant sí


def test_tasa_igual_al_umbral_pasa(sin_sleep):
    # Borde documentado: bloquea solo `tasa < umbral`; el empate exacto pasa.
    # Ventana 5 con 4 éxitos y 1 fallo = 80% == umbral 0.8.
    agente = crear_agente(client)
    _crear_politica("pol-empate", umbral=0.8, ventana=5)
    _sembrar_fallos(agente, 1)
    _sembrar_exitos(agente, 4)
    r = _promover_a_prod_como_admin(agente)
    assert r.status_code == 200


def test_gate_no_aplica_a_staging():
    # Decisión abierta #1: el gate solo protege prod; dev→staging sigue
    # quedando 'pendiente' aunque el agente tenga fallos y haya política.
    agente = crear_agente(client)
    _crear_politica("pol-staging-libre")
    _sembrar_fallos(agente, 3)
    r = client.post(
        f"/api/v1/agents/{agente}/promote",
        headers=_headers_admin("viewer_a"),
        json={
            "ambiente_origen": "dev",
            "ambiente_destino": "staging",
            "solicitante": "dev1",
            "rol_solicitante": "DEVELOPER",
        },
    )
    assert r.status_code == 200
    assert r.json()["promotion"]["estado"] == "pendiente"


def test_release_gate_sin_umbral_da_422():
    # Validación fail-fast al configurar: umbral=None evaluado en caliente
    # sería un TypeError en pleno promote.
    r = client.post(
        "/api/v1/governance/policies",
        json={
            "id": "pol-sin-umbral",
            "tenant_id": "tenant_a",
            "nombre": "gate roto",
            "descripcion": "sin umbral",
            "severidad": "alta",
            "tipo": "release_gate",
            "metrica": "tasa_exito_despliegues",
        },
        headers=_headers_admin(),
    )
    assert r.status_code == 422
    assert "umbral" in r.json()["detail"]


def test_tipo_desconocido_da_422():
    # `tipo` es Literal: un typo como "release-gate" crearía una política que
    # el gate jamás consulta (bypass silencioso). Se rechaza al crear.
    r = client.post(
        "/api/v1/governance/policies",
        json={
            "id": "pol-typo-tipo",
            "tenant_id": "tenant_a",
            "nombre": "gate con typo",
            "descripcion": "",
            "severidad": "alta",
            "tipo": "release-gate",
            "metrica": "tasa_exito_despliegues",
            "umbral": 0.8,
        },
        headers=_headers_admin(),
    )
    assert r.status_code == 422


def test_politica_con_id_duplicado_da_409():
    _crear_politica("pol-duplicada")
    r = client.post(
        "/api/v1/governance/policies",
        json={
            "id": "pol-duplicada",
            "tenant_id": "tenant_a",
            "nombre": "repetida",
            "descripcion": "",
            "severidad": "media",
        },
        headers=_headers_admin(),
    )
    assert r.status_code == 409


def test_politicas_persisten_y_se_listan_por_tenant():
    # El router de gobernanza ahora persiste en SQLite y filtra por tenant
    # con la misma forma de respuesta que la versión en memoria.
    _crear_politica("pol-listado-a", tenant_id="tenant-listado-a")
    _crear_politica("pol-listado-b", tenant_id="tenant-listado-b")

    todas = client.get("/api/v1/governance/policies").json()["policies"]
    ids = {p["id"] for p in todas}
    assert {"pol-listado-a", "pol-listado-b"} <= ids

    del_tenant = client.get("/api/v1/governance/tenant/tenant-listado-a").json()
    assert del_tenant["tenant"] == "tenant-listado-a"
    assert [p["id"] for p in del_tenant["policies"]] == ["pol-listado-a"]


# Cuerpo válido a propósito: así el único motivo de fallo es la auth (401/403),
# no una validación de schema (422). Crear una política puede frenar prod, por
# eso el POST exige rol ADMIN.
_POLITICA_VALIDA = {
    "id": "pol-auth",
    "tenant_id": "tenant_a",
    "nombre": "gate auth",
    "descripcion": "",
    "severidad": "alta",
    "tipo": "release_gate",
    "metrica": "tasa_exito_despliegues",
    "umbral": 0.8,
}


def test_crear_politica_sin_token_da_401():
    r = client.post("/api/v1/governance/policies", json=_POLITICA_VALIDA)
    assert r.status_code == 401


def test_crear_politica_con_rol_no_admin_da_403():
    r = client.post(
        "/api/v1/governance/policies",
        json=_POLITICA_VALIDA,
        headers=_headers_admin("viewer_a"),
    )
    assert r.status_code == 403


def test_gate_con_ventana_none_usa_default(sin_sleep):
    # ventana=None es válida y el gate cae al VENTANA_DEFAULT (5). Con 3 fallos
    # en esa ventana la tasa (0%) no supera el umbral y bloquea con 409.
    agente = crear_agente(client)
    _crear_politica("pol-ventana-none", ventana=None)
    _sembrar_fallos(agente, 3)
    r = _promover_a_prod_como_admin(agente)
    assert r.status_code == 409


def test_endpoint_vulnerable_fuga_politicas_cross_tenant():
    # Demo de pen-testing (ruta *-vulnerable): NO filtra por tenant, así que
    # devuelve políticas de otros tenants. Se verifica el comportamiento tal cual.
    _crear_politica("pol-vuln-a", tenant_id="tenant-vuln-a")
    _crear_politica("pol-vuln-b", tenant_id="tenant-vuln-b")
    fuga = client.get(
        "/api/v1/governance/tenant/tenant-vuln-a/policies-vulnerable"
    ).json()
    ids = {p["id"] for p in fuga["policies"]}
    assert {"pol-vuln-a", "pol-vuln-b"} <= ids  # fuga cross-tenant deliberada
