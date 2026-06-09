from jose import jwt
from passlib.context import CryptContext
from fastapi import HTTPException
from datetime import datetime, timedelta
from jose import jwt

CLAVE_DEBIL = "1234"
CLAVE_SECRETA = "agente123"
ALGORITMO = "HS256"

bcrypt_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

def crear_token(usuario, rol, tenant):

    datos = {
        "sub": usuario,
        "rol": rol,
        "tenant": tenant,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }

    return jwt.encode(
        datos,
        CLAVE_SECRETA,
        algorithm=ALGORITMO
    )

def hashear_password(password: str):
    return bcrypt_context.hash(password)

def verificar_admin(token):
    datos = jwt.decode(
        token,
        CLAVE_SECRETA,
        algorithms=[ALGORITMO]
    )

    rol = datos.get("rol")

    if rol != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado"
        )

    return True

def crear_token_vulnerable(usuario, rol, tenant):

    datos = {
        "sub": usuario,
        "rol": rol,
        "tenant": tenant
    }

    return jwt.encode(
        datos,
        CLAVE_DEBIL,
        algorithm="HS256"
    )

def obtener_datos_token(token):

    datos = jwt.decode(
        token,
        CLAVE_SECRETA,
        algorithms=[ALGORITMO]
    )

    return datos