"""Reloj del Módulo 2 (RF06).

Función inyectable para que los tests simulen el paso del tiempo
(monkeypatch de ahora_utc) y verifiquen la expiración de promociones a
las 24h sin esperas reales.
"""

from datetime import datetime, timezone


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)
