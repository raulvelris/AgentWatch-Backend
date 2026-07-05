"""Dependencias de autenticación del Módulo 2 (Despliegue / CI-CD).

Reutiliza el JWT del Módulo 4: importa obtener_datos_token() de
autenticacion_serv (no se reescribe nada de su lógica). El token viaja en
el header estándar `Authorization: Bearer <token>` — a diferencia de los
endpoints demo del Módulo 4, que lo reciben como query param; ese patrón
no se replica aquí.

Seam para RF13 (José/Módulo 4): cuando el front envíe el token, estas
dependencias entregan la identidad real sin tocar los routers.
"""

from fastapi import Depends, Header, HTTPException
from jose import JWTError

from app.services.autenticacion_serv import obtener_datos_token


def get_current_claims(
    authorization: str | None = Header(default=None),
) -> dict | None:
    """Claims del JWT ({sub, rol, tenant, exp}) si llega el header
    Authorization; None si no llega (los flujos demo sin login y los tests
    existentes siguen funcionando). Token inválido o expirado → 401.

    Nota: los tokens de /login-vulnerable están firmados con CLAVE_DEBIL
    (demo de pen-testing del Módulo 4) y aquí dan 401 — es deliberado:
    solo el camino seguro (/login) emite tokens válidos."""
    if authorization is None:
        return None
    esquema, _, token = authorization.partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Header Authorization inválido: se espera 'Bearer <token>'",
        )
    try:
        return obtener_datos_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


def get_current_role(
    claims: dict | None = Depends(get_current_claims),
) -> str | None:
    """Rol del usuario autenticado ("ADMIN" | "VIEWER") o None sin token."""
    return claims.get("rol") if claims else None


def require_admin(
    claims: dict | None = Depends(get_current_claims),
) -> dict:
    """Exige un token válido con rol ADMIN. get_current_claims ya lanza 401
    cuando el header o el token son inválidos; aquí 401 si no llegó ningún
    token, y 403 si el token es válido pero el rol no es ADMIN.

    A diferencia de environments.promote(), no hay fallback por body: el
    sentido de esta dependencia es cerrar el endpoint, así que sin token no
    se pasa."""
    if claims is None:
        raise HTTPException(
            status_code=401,
            detail="Se requiere autenticación: token Bearer con rol ADMIN",
        )
    if str(claims.get("rol", "")).upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Se requiere rol ADMIN")
    return claims


def require_authenticated(
    claims: dict | None = Depends(get_current_claims),
) -> dict:
    """Exige un token válido, de cualquier rol. 401 si no llega token (o si es
    inválido, que get_current_claims ya rechaza). Devuelve los claims.

    La usa promote(): promover no es solo de ADMIN (un usuario común pide una
    promoción que queda 'pendiente'); lo que exige ADMIN es el destino prod, y
    eso lo chequea el propio promote sobre el rol de los claims."""
    if claims is None:
        raise HTTPException(
            status_code=401,
            detail="Se requiere autenticación: token Bearer",
        )
    return claims
