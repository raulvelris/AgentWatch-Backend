from fastapi import APIRouter
from datetime import datetime
from app.services.autenticacion_serv import obtener_datos_token
from fastapi import HTTPException

router = APIRouter(
    prefix="/api/v1/security",
    tags=["Security"]
)

attack_logs = []


@router.get("/reports")
def list_security_reports():
    return {
        "reports": [
            {
                "id": "sec-001",
                "herramienta": "Semgrep",
                "paquete": "app/routers/agents.py",
                "version_vulnerable": "N/A",
                "version_segura": "N/A",
                "severidad": "Medium",
                "descripcion": "Posible validación insuficiente en endpoint de creación de agentes.",
                "estado": "Completado",
                "bloquea_merge": False,
                "tiempo": "1 min 12 s"
            },
            {
                "id": "sec-002",
                "herramienta": "OWASP Dependency-Check",
                "paquete": "fastapi",
                "version_vulnerable": "0.136.3",
                "version_segura": "0.136.4",
                "severidad": "High",
                "descripcion": "Dependencia con vulnerabilidad conocida simulada para demostración.",
                "estado": "Completado",
                "bloquea_merge": True,
                "tiempo": "2 min 34 s"
            },
            {
                "id": "sec-003",
                "herramienta": "Quality Gate",
                "paquete": "pipeline",
                "version_vulnerable": "N/A",
                "version_segura": "N/A",
                "severidad": "High",
                "descripcion": "El merge queda bloqueado por hallazgos High/Critical.",
                "estado": "Bloqueado",
                "bloquea_merge": True,
                "tiempo": "5 s"
            }
        ]
    }


def detectar_prompt_injection(texto: str):

    patrones_peligrosos = [
        "ignore previous instructions",
        "bypass",
        "system prompt",
        "jailbreak"
    ]

    texto = texto.lower()

    for patron in patrones_peligrosos:
        if patron in texto:
            return True

    return False


@router.get("/prompt-check")
def prompt_check(prompt: str):

    ataque = detectar_prompt_injection(prompt)

    if ataque:

        attack_logs.append({
            "tipo": "PROMPT_INJECTION",
            "prompt": prompt,
            "fecha": datetime.now().isoformat()
        })

        return {
            "bloqueado": True,
            "mensaje": "Prompt injection detectado"
        }

    return {
        "bloqueado": False,
        "mensaje": "Prompt aceptado"
    }


@router.get("/attack-logs")
def get_attack_logs():

    return {
        "logs": attack_logs
    }

#vulnerabilidad
@router.get("/admin-only")
def admin_only(token: str):

    attack_logs.append({
        "tipo": "ACCESS_ATTEMPT",
        "token": token,
        "fecha": datetime.now().isoformat()
    })

    return {
        "message": "Zona administrativa"
    }

@router.get("/admin-only-secure")
def admin_only_secure(token: str):

    datos = obtener_datos_token(token)

    if datos["rol"] != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado"
        )

    return {
        "usuario": datos["sub"],
        "rol": datos["rol"],
        "acceso": "PERMITIDO"
    }

@router.get("/admin-only-vulnerable")
def admin_only_vulnerable(token: str):

    datos = obtener_datos_token(token)

    return {
        "usuario": datos["sub"],
        "rol": datos["rol"],
        "acceso": "PERMITIDO"
    }

@router.get("/whoami")
def whoami(token: str):

    datos = obtener_datos_token(token)

    return {
        "usuario": datos.get("sub"),
        "rol": datos.get("rol"),
        "tenant": datos.get("tenant")
    }