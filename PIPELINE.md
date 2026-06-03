# PIPELINE.md — CI/CD del Módulo 2 (Despliegue, RF08)

Documentación del pipeline de integración y entrega continua del backend AgentWatch.
Todo el pipeline está definido como código en `.github/workflows/` (sin pasos manuales fuera
del repositorio).

## Flujo

```
PR ──► ci.yml ──────────────► merge a develop ──► deploy-staging.yml ──► (tag/dispatch) ──► deploy-prod-canary.yml
       lint                                        build + deploy staging                    10% ─► 50% ─► 100%
       tests + cobertura ≥70%                                                                Prometheus vigila error rate
       Semgrep (0 Critical/High)                                                             rollback auto si > 2%
       build imagen
```

## 1. `ci.yml` — Quality gate (dispara en cada PR)
- **lint** con `ruff`.
- **tests** con `pytest` y **gate de cobertura ≥ 70%** sobre los módulos del Módulo 2
  (`deployments`, `versions`, `environments`, schemas).
- **análisis estático** con **Semgrep**; bloquea ante hallazgos Critical/High.
- **build** de la imagen Docker.
- Se configura como *required status check* en la rama protegida → el merge queda bloqueado si
  algo falla.

## 2. `deploy-staging.yml` — Despliegue a staging (push a `develop`)
- Build de imagen y despliegue al ambiente `staging`.
- Usa el *environment* `staging` de GitHub para trazabilidad.
- Los pasos de Azure Container Apps están documentados como placeholder (requieren credenciales
  de Azure como secrets); ver ADR-02.1.

## 3. `deploy-prod-canary.yml` — Producción con canary (RF08)
- Estrategia **canary**: enruta **10% → 50% → 100%** del tráfico (revisions de Azure Container
  Apps), con **ventanas de 5 minutos** entre fases.
- En cada fase, **Prometheus** vigila el *error rate* de la revisión canary.
- Si el error rate supera **2%**, se ejecuta **rollback automático** a la revisión anterior.
- Requiere aprobación vía *environment* `production`.

## Nota de alcance (prototipo académico)
La estructura del pipeline y los quality gates son reales y ejecutables. Los pasos de despliegue
a Azure están documentados como placeholders porque requieren una suscripción/credenciales de
Azure; la lógica de despliegue (orquestación, versionado, rollback) vive y se demuestra en el
backend FastAPI. Ver la sección 4.2 (ADRs) y 5.2 (tácticas) de la documentación del Módulo 2.
