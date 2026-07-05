# AgentWatch Backend

API de AgentWatch, plataforma para diseñar, gobernar, desplegar y observar agentes
de IA dentro de una empresa. Proyecto del curso Arquitectura de Software
(Universidad de Lima, Grupo 3, 2026). El contexto general y el equipo están en el
README del frontend (`AgentWatch-Web`) y la documentación de arquitectura en el
repositorio `arqui261-grupo3`.

Este backend monta todos los módulos del sistema en un solo proceso.

## Stack

- FastAPI + Uvicorn
- SQLite con SQLAlchemy (persistencia del Módulo 2: versiones, promociones,
  despliegues, variables cifradas, políticas)
- JWT (python-jose) para autenticación
- Python 3.11

## Cómo correrlo

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

La base SQLite se crea sola al arrancar. La documentación interactiva de la API
queda en `http://127.0.0.1:8000/docs`.

Todo tiene valores por defecto, así que levanta sin configurar nada. Para que
ciertos datos sobrevivan reinicios o para producción, copiá `.env.example` a `.env`
y ajustá lo que haga falta: `DATABASE_URL`, `ENVVARS_KEY` (clave Fernet de las
variables cifradas), `NEO4J_*` (opcional, para las trazas), `JWT_SECRET`,
`CORS_ORIGINS`.

## Autenticación

Login de demo: `GET /api/v1/auth/login?usuario=admin_a` devuelve un JWT. Usuarios
de ejemplo: `admin_a` (rol ADMIN) y `viewer_a` (rol VIEWER). El token viaja en el
header `Authorization: Bearer <token>`.

Control de acceso del Módulo 2: desplegar, hacer rollback, promover a prod, crear
políticas de gobernanza y guardar variables exigen rol ADMIN. Promover a dev o
staging exige un token válido de cualquier rol. Los GET de lectura quedan
abiertos.

## Qué monta

Un solo proceso sirve todos los módulos:

- Diseño y gobernanza de agentes: `/agents`, `/templates`, `/governance`,
  `/security` (RF01-RF04).
- Despliegue y CI/CD: `/agents/{id}/deploy`, `/versions`, `/rollback`, `/promote`,
  `/environments/{env}/vars`, `/notifications` (RF05-RF08).
- Seguridad e identidad: `/auth`, `/tenants` (RF13-RF16).
- Observabilidad: `/traces`, `/audit`, `/metrics`, `/executions` (RF17-RF20).
  Requieren Neo4j (`NEO4J_URI`); sin esa variable responden 503 y el resto de la
  API sigue funcionando.

## Tests y CI

```bash
pytest tests/
```

La suite del Módulo 2 corre en verde. El pipeline (`.github/workflows/ci.yml`)
hace lint (ruff), tests con cobertura (gate mínimo 70%), análisis estático
(Semgrep) y build de la imagen Docker en cada PR. El detalle del flujo de CI/CD y
sus decisiones de diseño están en `PIPELINE.md`.

## Estado del proyecto

Prototipo académico. El pipeline de despliegue y el canary a producción están
simulados (declarado en `PIPELINE.md` y en los comentarios del código); el cifrado
de variables usa Fernet local como stand-in de Azure Key Vault. Lo implementado
funciona de punta a punta y está cubierto por tests.
