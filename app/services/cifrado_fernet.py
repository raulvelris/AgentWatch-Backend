"""Servicio de cifrado Fernet como stand-in local de Azure Key Vault (ADR-02.6).

Implementa la misma semántica observable que Key Vault: la BD solo almacena
ciphertext, la API enmascara los valores, la clave de cifrado vive fuera del
almacén de datos (variable de entorno `ENVVARS_KEY`). Reproduce la propiedad de
seguridad que mide EC-02.5 (0% de secretos en texto plano en la BD).

Punto de reemplazo: cuando exista la suscripción de Azure, este módulo se
sustituye por el cliente de Key Vault sin cambiar el contrato de la API
(la ADR-02.4 —Key Vault en producción— no cambia).
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# Si no hay clave configurada (ENVVARS_KEY), se genera una por proceso (solo
# desarrollo): los valores cifrados no sobreviven un reinicio del backend.
# En producción ENVVARS_KEY debe estar en .env.
_clave_fernet: bytes | None = None


class ErrorDescifrado(Exception):
    """La clave actual no puede descifrar el ciphertext guardado: ENVVARS_KEY
    cambió o no coincide con la usada al cifrar (por ejemplo, la clave efímera
    se perdió tras un reinicio sin ENVVARS_KEY configurada). El router la
    traduce a un 503, en vez de dejar subir la InvalidToken como 500 crudo."""


def _get_fernet() -> Fernet:
    global _clave_fernet
    if settings.ENVVARS_KEY:
        return Fernet(settings.ENVVARS_KEY.encode())
    # Modo desarrollo: clave efímera en memoria, estable dentro del proceso.
    if _clave_fernet is None:
        _clave_fernet = Fernet.generate_key()
    return Fernet(_clave_fernet)


def cifrar(valor: str) -> str:
    """Cifra un valor en texto plano y devuelve el token Fernet (base64)."""
    return _get_fernet().encrypt(valor.encode()).decode()


def descifrar(token: str) -> str:
    """Descifra un token Fernet y devuelve el valor original en texto plano.

    Si la clave actual no descifra el token (cambió o se perdió la efímera),
    Fernet lanza InvalidToken; se traduce a ErrorDescifrado para que el router
    responda un 503 claro y no un 500 crudo."""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ErrorDescifrado(
            "No se pueden descifrar las variables: la clave ENVVARS_KEY no "
            "coincide con la usada al guardarlas (cambió o no está configurada)."
        ) from exc


def enmascarar(valor_plano: str) -> str:
    """Devuelve el valor enmascarado para exponer en la API (nunca el plano).

    Muestra a lo sumo los primeros 4 caracteres como pista; el resto es `***`.
    """
    if len(valor_plano) <= 4:
        return "***"
    return valor_plano[:4] + "***"
