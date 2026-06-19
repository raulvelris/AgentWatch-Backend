"""Configuración central de la aplicación (pydantic-settings).

Todas las variables pueden sobreescribirse vía entorno o archivo .env
(ver .env.example en la raíz del repo). Los defaults permiten levantar
el backend en local sin configurar nada.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Módulo 2 (Despliegue / CI-CD) ---
    # SQLite embebido: inmutabilidad RF07 garantizada con triggers a nivel
    # de BD; migrar a PostgreSQL es cambiar esta URL (mismo ORM).
    DATABASE_URL: str = "sqlite:///./agentwatch.db"

    # Orígenes CORS permitidos, separados por coma.
    # Para exponer el backend a un celular en la misma red WiFi, agregar la
    # IP local en .env (ver .env.example); no hardcodear IPs personales aquí.
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8081,http://127.0.0.1:8081"
    )

    # RF06/ADR-02.6: clave Fernet para cifrar las variables de entorno por
    # ambiente. Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Sin esta variable, cifrado_fernet genera una clave efímera en memoria
    # (solo desarrollo; los valores no sobreviven reinicios). En producción,
    # SIEMPRE definirla en .env — es la "clave fuera del almacén" de EC-02.5.
    ENVVARS_KEY: str | None = None

    # --- Módulo 5 (Trazabilidad, Gabriel) — opcionales ---
    # Sin NEO4J_URI los endpoints /traces, /audit, /metrics y /executions
    # responden 503 ("Neo4j no configurado"); el resto de la API funciona.
    NEO4J_URI: str | None = None
    NEO4J_USER: str | None = None
    NEO4J_PASSWORD: str | None = None
    NEO4J_DATABASE: str = "neo4j"

    # --- Módulo 4 (Seguridad, Emilio) ---
    # Declarada aquí para cuando autenticacion_serv.py la lea de entorno
    # (pendiente de Emilio); el default replica la clave actual para no
    # invalidar tokens existentes.
    JWT_SECRET: str = "agente123"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
