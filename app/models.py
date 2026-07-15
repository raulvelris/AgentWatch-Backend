"""Modelos SQLAlchemy del Módulo 2 (Despliegue / CI-CD).

Tablas del Módulo 2 (RF05-RF07): versiones, promociones, registros de
despliegue y outbox de notificaciones; más `PolicyDB` (Gobernanza), que el
release gate de calidad consulta al promover a prod. Los agents/templates
de otros módulos siguen en memoria (no son de este módulo).
"""

from sqlalchemy import Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class AgentDB(Base):
    """Configuración persistente completa de un agente.

    `config_json` conserva todos los campos del AgentConfig como un JSON
    canónico. Esto permite recuperar la configuración real durante el deploy
    y calcular el hash SHA-256 de RF07.
    """

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    owner: Mapped[str] = mapped_column(String)
    nombre: Mapped[str] = mapped_column(String)
    tipo: Mapped[str] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String, default="DRAFT")
    config_json: Mapped[str] = mapped_column(Text)

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
    """Outbox de notificaciones (RF22 / Módulo 6): notificaciones push con
    3 niveles de criticidad (CRITICAL, WARNING, INFO). El campo `criticidad`
    es el nivel formal del CA-01; `tipo` es la causa semántica del evento.
    El backend encola; el envío real lo despacha NotificationService (FCM)."""

    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # "promotion_pendiente" | "promotion_expirada" | "deploy_fallido"
    tipo: Mapped[str] = mapped_column(String, index=True)
    # RF22 CA-01: nivel formal de criticidad → "CRITICAL" | "WARNING" | "INFO"
    criticidad: Mapped[str] = mapped_column(String, index=True, default="INFO", server_default="INFO")
    destinatario_rol: Mapped[str] = mapped_column(String, index=True)
    mensaje: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    fecha: Mapped[str] = mapped_column(String)  # ISO-8601 UTC
    leida: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class PolicyDB(Base):
    """Políticas de gobernanza (release gate de calidad sobre promote a prod).

    A diferencia de VersionDB (RF07), esta tabla es MUTABLE por diseño: una
    política es configuración viva (se activa o desactiva), no un registro
    histórico de auditoría — por eso NO lleva triggers de inmutabilidad.

    `tipo="release_gate"` + `metrica`/`umbral`/`ventana` definen el gate que
    evalúa governance_service.evaluar_gate_promocion() antes de promover a
    prod. `tipo="informativa"` (default) replica el comportamiento previo:
    la política existe pero no bloquea nada.
    """

    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nombre: Mapped[str] = mapped_column(String)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    severidad: Mapped[str] = mapped_column(String, default="media")
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    # "informativa" (default, no bloquea) | "release_gate" (bloquea promote a prod)
    tipo: Mapped[str] = mapped_column(String, default="informativa")
    # Para release_gate: métrica soportada "tasa_exito_despliegues",
    # umbral en [0, 1] y ventana = últimos N despliegues considerados.
    metrica: Mapped[str | None] = mapped_column(String, nullable=True)
    umbral: Mapped[float | None] = mapped_column(Float, nullable=True)
    ventana: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
