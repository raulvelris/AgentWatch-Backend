Copiar todo el texto de abajo (desde "Contexto" hasta el final) y pegarlo como
prompt inicial en Claude Code, con este repo (`AgentWatch-Backend`) como
directorio de trabajo.

---

## Contexto del proyecto

Estás trabajando en `AgentWatch-Backend`, el backend de un proyecto
universitario (curso de Arquitectura de Software) llamado AgentWatch: una
plataforma para gestionar el ciclo de vida de "agentes" (automatizaciones/
agentes configurables — no modelos de ML entrenados). Backend en FastAPI +
SQLAlchemy + SQLite, dividido en módulos por integrante del equipo:

- **Módulo 2 (el mío, RF05/RF06/RF07)**: despliegue con log en vivo
  (`app/routers/deployments.py`), ambientes y promoción entre dev/staging/prod
  (`app/routers/environments.py`), versionado inmutable con rollback
  (`app/routers/versions.py`), variables de entorno cifradas
  (`app/routers/env_vars.py`). Persistencia en SQLite vía SQLAlchemy
  (`app/models.py`, `app/core/database.py`). RF07 garantiza inmutabilidad del
  historial de versiones con triggers a nivel de base de datos (ver
  `app/core/database.py`) — no repliques ese patrón de triggers para lo que
  te voy a pedir, porque es específico de auditoría histórica, no aplica a
  configuración viva como políticas.
- **Módulo 4**: autenticación JWT (`app/routers/autenticacion.py`), tenants,
  seguridad. El helper `app/services/deps.py::get_current_claims` da los
  claims del JWT si llega `Authorization: Bearer <token>`, o `None` si no.
- **Módulo 5 (de un compañero, Gabriel)**: trazabilidad en Neo4j, vive en el
  subpaquete `rf17_rf20_gabriel/`, es opcional (sin `NEO4J_URI` configurado,
  sus endpoints responden 503). **No lo toques ni dependas de él.**
- **Gobernanza** (`app/routers/governance.py` +
  `app/services/governance_service.py`): módulo de políticas. Existe el
  router y el schema `Policy`, pero **nada más del repo los usa**, y
  `governance_service.py` está vacío (1 línea).

Antes de escribir nada, leé estos archivos para entender los patrones y
convenciones reales del repo (nombres de campos en español, snake_case,
comentarios que referencian RF/ADR, manejo de sesiones SQLAlchemy con
`with get_session() as session:`):

- `app/models.py`
- `app/core/database.py`
- `app/routers/environments.py`
- `app/routers/versions.py`
- `app/routers/deployments.py`
- `app/routers/governance.py`
- `app/schemas/policy.py`
- `tests/test_modulo2_despliegue.py`
- `docs/plan-mlops-release-gate.md` (el plan completo de lo que sigue — LEELO ENTERO antes de empezar, es la base de todo este prompt)

## Objetivo

Implementar un **release gate de calidad**: la promoción de un agente a
producción (`POST /api/v1/agents/{agent_id}/promote` con
`ambiente_destino=prod`) debe, además de exigir rol ADMIN (regla ya
existente — no la toques), consultar políticas de gobernanza (`PolicyDB`,
`tipo="release_gate"`) y **bloquear la promoción incluso para un ADMIN** si
el agente no cumple el umbral de calidad definido (medido como tasa de éxito
de sus últimos N despliegues, usando la tabla `despliegues` /
`DeploymentRecordDB`, que ya existe y ya se llena sola en cada deploy).

El diseño detallado, el modelo de datos propuesto y el pseudocódigo de
referencia están en `docs/plan-mlops-release-gate.md`. Ese documento es tu
punto de partida, no un dogma: quiero que lo audites antes de implementarlo
(ver Paso 1 abajo).

## Decisiones ya tomadas (validadas conmigo, no las reabras)

- Las políticas se persisten en SQLite (tabla nueva `PolicyDB`), no en
  memoria.
- El gate NO depende de Neo4j ni del módulo RF19 de mi compañero — tiene que
  quedar 100% autocontenido, usando solo datos que ya genera este módulo.
- El bloqueo es duro: un ADMIN también queda bloqueado si el agente no pasa
  el gate. No implementes ningún mecanismo de override ni de excepción.
- Compatibilidad hacia atrás obligatoria: si no hay ninguna política activa
  de tipo `release_gate` para el tenant, el comportamiento tiene que ser
  IDÉNTICO al actual. No podés romper ninguno de los 8 tests que ya existen
  en `tests/test_modulo2_despliegue.py`.

## Lo que quiero que decidas vos (marcado como abierto en el plan)

- Si el gate aplica solo a promociones hacia `prod`, o también hacia
  `staging`.
- Qué hacer cuando un agente no tiene ningún despliegue previo (sin datos
  para calcular la tasa de éxito).
- Cómo resolver el `tenant_id`, dado que `VersionDB`, `PromotionDB` y
  `DeploymentRecordDB` no tienen columna `tenant_id` hoy.

El plan trae una propuesta para cada una de estas tres. Podés usarla, pero
solo si después de pensarla te parece razonable — no la copies por copiarla.

## Cómo quiero que trabajes, en este orden

**1. Auditoría crítica del plan (antes de tocar código).**
Leé `docs/plan-mlops-release-gate.md` completo y decime, ANTES de escribir
una sola línea: ¿es la mejor forma de resolver esto, o hay un enfoque más
simple o más robusto? Buscá específicamente:
- Problemas de concurrencia (SQLite + FastAPI corriendo en threadpool).
- Casos borde que el plan no cubre.
- Inconsistencias con patrones ya usados en el repo.
- Cualquier decisión del plan que te parezca arbitraria o mal justificada.
No implementes nada en este paso. Primero decime qué encontraste y esperá
mi confirmación si algo de lo que proponés cambia el diseño de forma
importante.

**2. Sé proactivo más allá de lo pedido.**
Si notás algo relacionado —en `environments.py`, `governance.py`, o en cómo
interactúan los módulos— que esté mal, sea inconsistente, o sea una mejora
obvia que no te pedí, señalámelo. No lo implementes sin decírmelo primero,
pero quiero que lo menciones igual.

**3. Línea base.**
Antes de tocar código, corré `pytest` y confirmame que los 8 tests de
`tests/test_modulo2_despliegue.py` pasan en el estado actual del repo.

**4. Implementación.**
Implementá el cambio usando el pseudocódigo del plan como guía, no como
receta literal — mejoralo donde corresponda, pero decime explícitamente qué
cambiaste respecto al plan original y por qué.

**5. Tests nuevos.**
Escribí tests que cubran como mínimo: (a) sin políticas de gate activas el
comportamiento es idéntico al actual, (b) una promoción se bloquea cuando la
tasa de éxito está por debajo del umbral, incluso siendo ADMIN, (c) se
desbloquea cuando la tasa sube, (d) un agente sin historial de despliegues,
(e) una política inactiva no bloquea nada, (f) una política de otro tenant
no afecta al tenant actual.

**6. Verificación final.**
Corré toda la suite de nuevo (los 8 tests viejos + los nuevos). Si algo se
rompe, arreglalo antes de darme el resultado como terminado. No me entregues
código con tests en rojo.

**7. Resumen de cierre.**
Cerrá con: qué archivos tocaste, qué decidiste en los tres puntos abiertos y
por qué, qué encontraste en la auditoría del paso 1, y si quedó algo
pendiente o dudoso.

## Regla más importante de todas

Si en cualquier momento algo en este prompt, en el plan, o en lo que
encontrás en el código real te resulta contradictorio, ambiguo, o no
coincide con lo que se describe acá, **PARÁ y preguntame directamente**. No
asumas cuál es "la verdad" ni improvises una interpretación en silencio.
Preferí siempre una pregunta corta mía por sobre una suposición tuya, incluso
si te parece una decisión menor.
