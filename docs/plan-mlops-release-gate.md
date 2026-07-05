# Plan: Release Gate de calidad (MLOps aplicado a AgentWatch)

Autor del plan: Enzo (Módulo 2 — RF05/RF06/RF07).
Este documento es la base para: (1) el video explicativo, (2) el prompt que se le
entrega a la herramienta de generación de código para implementar.

---

## 1. Resumen para el video (lenguaje simple)

En MLOps, un modelo no pasa a producción solo porque alguien lo aprueba a ojo: el
sistema revisa métricas recientes y bloquea el ascenso si no las cumple. Eso se
llama un **release gate** (o gate de calidad).

AgentWatch hoy NO tiene eso. En `app/routers/environments.py`, la función
`promote()` deja pasar un agente a producción con una sola condición: *¿la persona
que lo pide tiene rol ADMIN?* Nada revisa si ese agente se viene comportando bien.

Lo interesante: el proyecto ya tiene un módulo de **Gobernanza**
(`app/routers/governance.py`) con un modelo `Policy` pensado exactamente para
reglas de este tipo. Existe, se puede crear políticas... pero nada las usa. Y
`app/services/governance_service.py` — el archivo que debería contener esa
lógica — está vacío.

Este plan conecta esas dos piezas: convierte `Policy` en algo que de verdad se
consulta antes de promover un agente a producción, usando datos que el propio
módulo ya genera (el historial de despliegues, éxito/fallo).

---

## 2. El hallazgo (para justificar el tema en la sustentación)

- `app/routers/environments.py::promote()` — única condición para `prod`:
  `rol.upper() == "ADMIN"`. Cero conexión con calidad o historial.
- `app/routers/governance.py` — políticas se crean y se listan, pero **ningún
  otro archivo del repo las importa ni las consulta**. Es un módulo aislado.
- `app/services/governance_service.py` — 1 línea, vacío.
- `app/models.py::DeploymentRecordDB` — ya guarda, por cada despliegue, el
  `resultado` ("success"/"failed"). Es la materia prima que falta usar.

Conclusión: el proyecto tiene todas las piezas para un gate de calidad real y
nadie las conectó. Ese es el gap que este tema de MLOps resuelve.

---

## 3. Decisiones ya tomadas (no reabrir estas)

| Decisión | Elegido | Por qué |
|---|---|---|
| Persistencia de políticas | SQLite (`PolicyDB`), no en memoria | Mismo patrón que `VersionDB`/`PromotionDB`/`DeploymentRecordDB`; sobrevive reinicios; el motor SQLAlchemy ya está listo. |
| Alcance | Autocontenido en Módulo 2 | Cero dependencia de Neo4j / RF19 (módulo de un compañero); cero riesgo de que el demo falle en cámara por infraestructura externa. |
| Bloqueo | Duro, sin excepción para ADMIN | Más simple de mostrar y explicar en el video: "ni el admin pasa si no cumple el umbral". No se implementa override. |
| Compatibilidad | Obligatoria | Sin políticas `release_gate` activas, el comportamiento debe ser IDÉNTICO al actual. No debe romper los 8 tests de `tests/test_modulo2_despliegue.py`. |

## 4. Decisiones abiertas (la herramienta debe confirmarlas con Enzo, no asumir)

1. ¿El gate aplica solo a promociones hacia `prod`, o también hacia `staging`?
   Propuesta de este plan: solo `prod` — es el único ambiente con protección
   especial hoy (el único que ya exige ADMIN).
2. ¿Qué pasa si el agente no tiene ningún despliegue previo (sin datos para
   calcular la tasa de éxito)? Propuesta: permitir por defecto — no se puede
   reprobar una métrica que todavía no existe.
3. Las tablas de este módulo (`VersionDB`, `PromotionDB`, `DeploymentRecordDB`)
   no tienen columna `tenant_id`. Propuesta: usar un tenant por defecto
   `"tenant_a"` (mismo default que `AgentConfig.tenant_id`), y documentarlo
   como limitación conocida — en un sistema multi-tenant real, cada versión y
   despliegue debería llevar su `tenant_id` explícito.

---

## 5. Diseño técnico

### 5.1 Modelo de datos nuevo (`app/models.py`)

```python
# Requiere agregar Boolean y Float al import existente de sqlalchemy.

class PolicyDB(Base):
    """Políticas de gobernanza. A diferencia de VersionDB, esta tabla es
    MUTABLE por diseño: una política es configuración viva (se activa o
    desactiva), no un registro histórico de auditoría. No lleva triggers
    de inmutabilidad."""

    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nombre: Mapped[str] = mapped_column(String)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    severidad: Mapped[str] = mapped_column(String, default="media")
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    # "informativa" (default, comportamiento actual) | "release_gate"
    tipo: Mapped[str] = mapped_column(String, default="informativa")
    metrica: Mapped[str | None] = mapped_column(String, nullable=True)
    umbral: Mapped[float | None] = mapped_column(Float, nullable=True)
    ventana: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

### 5.2 Schema (`app/schemas/policy.py`)

```python
class Policy(BaseModel):
    id: str
    tenant_id: str
    nombre: str
    descripcion: str
    severidad: str
    activa: bool = True
    tipo: str = "informativa"
    metrica: str | None = None
    umbral: float | None = None
    ventana: int | None = None
```

### 5.3 Servicio — pseudocódigo (`app/services/governance_service.py`)

```
function calcular_tasa_exito(agent_id, ventana):
    despliegues = últimos `ventana` DeploymentRecordDB de agent_id, orden desc por fecha
    si despliegues está vacío:
        retornar None            # "sin datos" (no es lo mismo que 0.0)
    exitosos = contar(resultado == "success")
    retornar exitosos / len(despliegues)

function evaluar_gate_promocion(tenant_id, agent_id):
    politicas = PolicyDB donde tenant_id=tenant_id, tipo="release_gate", activa=True
    si politicas vacío:
        retornar (aprobado=True, motivo="Sin políticas de gate activas")

    para cada politica en politicas:
        si politica.metrica == "tasa_exito_despliegues":
            tasa = calcular_tasa_exito(agent_id, politica.ventana o 5 por defecto)
            si tasa es None:
                continuar         # sin histórico -> esta política no bloquea (ver decisión abierta #2)
            si tasa < politica.umbral:
                retornar (aprobado=False,
                          motivo=f"Política '{politica.nombre}' no superada: "
                                 f"tasa de éxito {tasa:.0%} < umbral requerido {politica.umbral:.0%}")

    retornar (aprobado=True, motivo="Todas las políticas de gate superadas")
```

### 5.4 Cambios en `app/routers/environments.py::promote()`

```
...
es_admin = rol.upper() == "ADMIN"
if req.ambiente_destino == "prod" and not es_admin:
    raise 403 (SIN CAMBIOS — esta regla ya existe)

if req.ambiente_destino == "prod":
    aprobado, motivo = evaluar_gate_promocion(tenant_id_default, agent_id)
    if not aprobado:
        raise HTTPException(409, detail=motivo)
        # 409 Conflict, no 403: la persona SÍ tiene permiso (es ADMIN),
        # el problema es el estado/calidad del agente, no la identidad.
...
```

### 5.5 Cambios en `app/routers/governance.py`

Reemplazar la lista en memoria `policies_db` por persistencia real vía
`governance_service` (crear política → INSERT en `PolicyDB`; listar → SELECT).
Mantener la forma de respuesta JSON igual a la actual para no romper nada que
ya la consuma.

### 5.6 Tests nuevos (`tests/test_governance_gate.py`)

- `test_promote_sin_politicas_se_comporta_como_antes` — regresión: sin
  políticas `release_gate`, el flujo actual (403 sin admin / éxito con admin)
  no cambia.
- `test_promote_bloqueada_por_gate_aunque_sea_admin` — crear política
  `umbral=0.8`, sembrar despliegues fallidos con `?fallo=healthcheck` hasta
  bajar la tasa, intentar promover como ADMIN, esperar 409.
- `test_promote_pasa_gate_cuando_supera_umbral` — sembrar despliegues
  exitosos, la tasa sube, la promoción pasa.
- `test_gate_sin_historial_no_bloquea` — agente sin despliegues previos,
  política activa, promoción no debe bloquearse por falta de datos.
- `test_politica_inactiva_no_bloquea` — `activa=False` no debe afectar nada.
- `test_politica_de_otro_tenant_no_bloquea` — una política de un tenant
  distinto no debe aplicar al tenant actual.

---

## 6. Guion del video (instalar → mostrar el problema → mostrar la solución)

1. **Instalar**: `pip install -r requirements.txt` seguido de
   `uvicorn app.main:app --reload`. La base SQLite se crea sola
   (`init_db()` corre al importar la app). Mostrar `/docs`.
2. **Mostrar el problema en vivo**: forzar 3-4 despliegues fallidos con el
   parámetro que YA existe (`POST /api/v1/agents/{id}/deploy?fallo=healthcheck`),
   luego `POST /api/v1/agents/{id}/promote` a `prod` como ADMIN. Hoy pasa
   igual, sin filtro — ese es el "antes".
3. **Mostrar el cambio**: crear la política de gate. Este POST ahora exige rol
   ADMIN. Primero sacar un token con `GET /api/v1/auth/login?usuario=admin_a` y
   mandarlo en el header `Authorization: Bearer <token>`. Con ese token,
   `POST /api/v1/governance/policies` con una política `tipo="release_gate"`,
   `metrica="tasa_exito_despliegues"`, `umbral=0.8`. Sin token da 401 y con un
   token que no sea ADMIN da 403.
4. Repetir el mismo escenario de despliegues fallidos → ahora la promoción
   da 409, con el motivo explicado en la respuesta.
5. Mostrar que se puede desbloquear: correr despliegues exitosos, la tasa
   sube, la promoción pasa (200).
6. Opcional, solo mencionado de palabra (no implementado): este mismo gate
   podría más adelante consultar el ROI/calidad que calcula el módulo de
   trazas de un compañero (RF19, Neo4j), ya que corre en el mismo proceso.
   Se deja como "próximo paso" para mostrar visión de conjunto sin
   depender de infraestructura externa en la grabación.

---

## 7. Cosas honestas para decir en la sustentación (no esconder)

- El `tenant_id` por defecto es una simplificación reconocida: este módulo no
  tiene aislamiento multi-tenant real todavía en sus tablas.
- El diseño es "fail-open": si nadie configura una política, no bloquea nada.
  Es una decisión deliberada (no romper lo existente), no un descuido — pero
  vale la pena decir en voz alta que se pensó así a propósito.
- 409 en vez de 403 es una elección de semántica HTTP: permiso vs. estado.
  Vale la pena explicar por qué se eligió así.

---

> **Nota de mantenimiento (limpieza de repo):** los prompts de trabajo usados para
> implementar este release gate (`docs/prompt-*.md`) se removieron del repositorio.
> Eran instrucciones para una herramienta de generación de código, no documentación
> del proyecto, por lo que ahora viven fuera de cualquier repo, en la carpeta raíz
> `Agentwatch/` junto con `MEMORIA-AGENTWATCH.md`.
