"""Modelos SQLAlchemy del Módulo 2 (Despliegue / CI-CD).

Solo tablas del Módulo 2 (RF05-RF07): versiones, promociones, registros de
despliegue y outbox de notificaciones. Los agents/templates de otros
módulos siguen en memoria (no son de este módulo).
"""

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VersionDB(Base):
    """RF07: historial inmutable (triggers en database.py). `estado` es el
    único campo mutable: puntero de ciclo de vida (activa/inactiva/rollback/
    fallida) con una sola versión vigente por agente."""

    __tablename__ = "versiones"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    numero: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[str] = mapped_column(String)  # ISO-8601 UTC
    autor: Mapped[str] = mapped_column(String)
    hash_sha256: Mapped[str] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String, default="activa")
    descripcion: Mapped[str] = mapped_column(Text, default="")


class PromotionDB(Base):
    """RF06: solicitudes de promoción entre ambientes. Estados: aprobada |
    pendiente | expirada (>24h sin aprobar, evaluado al consultar)."""

    __tablename__ = "promociones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    ambiente_origen: Mapped[str] = mapped_column(String)
    ambiente_destino: Mapped[str] = mapped_column(String)
    solicitante: Mapped[str] = mapped_column(String)
    aprobado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    estado: Mapped[str] = mapped_column(String, default="pendiente")
    fecha: Mapped[str] = mapped_column(String)  # ISO-8601 UTC


class DeploymentRecordDB(Base):
    """RF05: registro auditable de TODO despliegue (exitoso o fallido):
    quién, cuándo, desde qué versión, resultado."""

    __tablename__ = "despliegues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    autor: Mapped[str] = mapped_column(String)
    fecha: Mapped[str] = mapped_column(String)  # ISO-8601 UTC
    version_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    version_desplegada: Mapped[str | None] = mapped_column(String, nullable=True)
    resultado: Mapped[str] = mapped_column(String)  # "success" | "failed"
    fase_fallo: Mapped[str | None] = mapped_column(String, nullable=True)


class NotificacionDB(Base):
    """Outbox de notificaciones (RF06): sustituto etiquetado del email/push
    que llegará con el Módulo 6. El backend solo ENCOLA; el envío real es
    responsabilidad futura del canal de notificaciones."""

    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # "promotion_pendiente" | "promotion_expirada" | "deploy_fallido"
    tipo: Mapped[str] = mapped_column(String, index=True)
    destinatario_rol: Mapped[str] = mapped_column(String, index=True)
    mensaje: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    fecha: Mapped[str] = mapped_column(String)  # ISO-8601 UTC


class AgentEnvVarDB(Base):
    """RF06/ADR-02.6: variables de entorno por ambiente, cifradas con Fernet
    como stand-in local de Azure Key Vault. La columna `valor_cifrado` solo
    almacena ciphertext (token Fernet `gAAA...`) — nunca texto plano (EC-02.5).
    La unicidad (agent_id, ambiente, nombre) habilita el upsert del PUT."""

    __tablename__ = "agent_env_vars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    ambiente: Mapped[str] = mapped_column(String)  # "dev" | "staging" | "prod"
    nombre: Mapped[str] = mapped_column(String)  # p. ej. "OPENAI_KEY"
    valor_cifrado: Mapped[str] = mapped_column(Text)  # token Fernet (base64)
    fecha: Mapped[str] = mapped_column(String)  # ISO-8601 UTC

    __table_args__ = (
        UniqueConstraint("agent_id", "ambiente", "nombre", name="uq_agent_env_var"),
    )
