from fastapi import APIRouter
from app.services.autenticacion_serv import crear_token
from app.services.autenticacion_serv import crear_token_vulnerable
router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

usuarios = {
    "admin_a": {
        "rol": "ADMIN",
        "tenant": "tenant_a"
    },

    "viewer_a": {
        "rol": "VIEWER",
        "tenant": "tenant_a"
    },

    "admin_b": {
        "rol": "ADMIN",
        "tenant": "tenant_b"
    },

    "viewer_b": {
        "rol": "VIEWER",
        "tenant": "tenant_b"
    }
}

@router.get("/login")
def login(usuario: str):

    usuario_data = usuarios.get(usuario)

    if not usuario_data:
        return {
            "error": "Usuario no existe"
        }

    rol = usuario_data["rol"]
    tenant = usuario_data["tenant"]

    token = crear_token(
        usuario,
        rol,
        tenant
    )

    return {
        "usuario": usuario,
        "rol": rol,
        "tenant": tenant,
        "token": token
    }

@router.get("/login-vulnerable")
def login_vulnerable(usuario: str):

    usuario_data = usuarios.get(usuario)

    if not usuario_data:
        return {
            "error": "Usuario no existe"
        }

    token = crear_token_vulnerable(
        usuario,
        usuario_data["rol"],
        usuario_data["tenant"]
    )

    return {
        "usuario": usuario,
        "rol": usuario_data["rol"],
        "tenant": usuario_data["tenant"],
        "token": token
    }