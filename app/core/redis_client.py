import os
import redis

# En Azure o Prod, REDIS_URL debería configurarse (ej. redis://mi-cache.redis.cache.windows.net:6380)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Creamos el pool de conexiones síncrono.
# Usamos decode_responses=True para que devuelva strings en lugar de bytes.
try:
    redis_db = redis.from_url(REDIS_URL, decode_responses=True)
except Exception:
    redis_db = None
