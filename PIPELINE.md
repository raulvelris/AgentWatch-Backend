# PIPELINE.md — CI/CD del Módulo 2 (Despliegue, RF08)

Documentación del pipeline de integración y entrega continua del backend AgentWatch.
Todo el pipeline está definido como código en `.github/workflows/` (sin pasos manuales fuera
del repositorio).

## Flujo

```
PR ──► ci.yml ──────────────► merge a develop ──► deploy-staging.yml ──► (tag/dispatch) ──► deploy-prod-canary.yml
       lint                                        build + deploy staging                    10% ─► 50% ─► 100%
       tests + cobertura ≥70%                      (deploy SIMULADO)                         (ejecución SIMULADA)
       Semgrep (0 Critical/High)
       build imagen
```

## Qué es real y qué es simulado

| Workflow | Paso | Estado |
|---|---|---|
| `ci.yml` | lint (ruff) | **REAL** (bloquea) |
| `ci.yml` | tests + cobertura ≥70% | **REAL** (bloquea) |
| `ci.yml` | Semgrep `--severity ERROR` | **REAL** (bloquea) |
| `ci.yml` | docker build | **REAL** |
| `deploy-staging.yml` | docker build | **REAL** |
| `deploy-staging.yml` | deploy a Azure + smoke test | **SIMULADO** (echo; `az` real comentado al lado) |
| `deploy-prod-canary.yml` | enrutado 10/50/100, ventana Prometheus, rollback | **SIMULADO** (echo; comandos reales comentados al lado) |
| `demo-pipeline.yml` | lint + tests | **REAL**, solo manual (`workflow_dispatch`) |

Cada paso simulado lo dice en su `name` con el sufijo **(SIMULADO)** y lleva el comando real
de Azure comentado junto al paso.

## 1. `ci.yml` — Quality gate (dispara en cada PR y push a develop)
- **lint** con `ruff` sobre `app` y `tests`.
- **tests** con `pytest` y **gate de cobertura ≥ 70%** sobre TODO el código del Módulo 2:
  routers (`deployments`, `versions`, `environments`, `notifications`), schemas, persistencia
  (`core.database`, `models`), configuración (`core.config`) y servicios (`deps`,
  `notificaciones`, `reloj`). Cobertura medida al ampliar el scope: **99%**.
- **análisis estático** con **Semgrep** (`--config auto --severity ERROR --error`); bloquea
  ante hallazgos Critical/High.
- **build** de la imagen Docker.
- Se configura como *required status check* en la rama protegida → el merge queda bloqueado si
  algo falla.

## 2. `deploy-staging.yml` — Despliegue a staging (push a `develop`)
- Build de imagen **real**.
- El despliegue a Azure Container Apps y el smoke test están **SIMULADOS** (echo): requieren
  una suscripción y credenciales de Azure como secrets. Los comandos `az`/`curl` reales están
  comentados junto a cada paso; ver ADR-02.1.
- Usa el *environment* `staging` de GitHub para trazabilidad.

## 3. `deploy-prod-canary.yml` — Producción con canary (RF08)
- Dispara solo por `workflow_dispatch` o tag `v*` (un canary de producción no corre en pushes
  de ramas de feature).
- Modela la estrategia **canary** 10% → 50% → 100% (matrix con `max-parallel: 1`) y requiere
  aprobación vía *environment* `production`.
- **TODA la ejecución está SIMULADA** (echo): el enrutado de tráfico, la ventana de observación
  de 5 minutos con Prometheus y el rollback automático ante error rate > 2% **no existen aún**;
  los comandos `az` reales están comentados junto a cada paso. Mientras los pasos sean echo,
  el paso de rollback (`if: failure()`) es inalcanzable.
- La lógica de despliegue que SÍ se demuestra funcionando (fallo controlado + revert automático
  + registro auditable) vive en el backend FastAPI (`POST /deploy?fallo=<fase>`, RF05).

## 4. `demo-pipeline.yml` — Demo para video
- Versión recortada (lint + tests) usada para una demo grabada.
- Solo manual (`workflow_dispatch`); antes corría en cada push de cualquier rama (corregido).

## Nota de alcance (prototipo académico)
Los quality gates de `ci.yml` son reales y ejecutables; los pasos de despliegue a Azure son
placeholders etiquetados **(SIMULADO)** porque requieren una suscripción/credenciales. La
orquestación de despliegue con camino de fallo, revert automático y registro auditable se
demuestra en el backend (RF05/RF07): versionado inmutable garantizado por triggers en BD y
historial persistente. Ver la sección 4.2 (ADRs) y 5.2 (tácticas) de la documentación del
Módulo 2.
