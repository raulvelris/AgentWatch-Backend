Copiar todo el texto de abajo (desde "Contexto" hasta el final) y pegarlo como
prompt en Claude Code, con `AgentWatch-Backend` como directorio de trabajo.
Es la continuación de `docs/prompt-implementacion-release-gate.md` — el release gate ya está
implementado y los tests pasan, pero nada quedó en una rama, ni commiteado,
ni pusheado.

---

## Contexto

Implementaste el release gate de calidad (governance_service.py,
PolicyDB, hook en `promote()`, tests nuevos) directamente sobre `main`, sin
crear rama ni commitear nada. Verifiqué el estado actual con `git status` y
encontré dos cosas que hay que resolver antes de abrir el PR:

1. **Nada está en una rama ni commiteado.** Todo son cambios sin stage sobre
   `main`. Hay que aislarlo en una rama propia antes de tocar nada más.

2. **`git status` muestra ~55 archivos modificados, pero la mayoría es ruido,
   no tu cambio real.** Verifiqué con `git diff --ignore-space-at-eol` que
   archivos como `tests/conftest.py`, `app/services/deps.py`, TODO
   `rf17_rf20_gabriel/`, los workflows de `.github/`, el `Dockerfile`, etc.
   tienen el mismo contenido línea por línea — el diff completo desaparece
   con esa flag. Es un cambio de fin de línea (CRLF vs LF) en el archivo
   completo, no una edición real. Confirmalo vos mismo antes de seguir (no
   asumas que tengo razón): `git diff --ignore-space-at-eol --stat`.

   Los ÚNICOS archivos con contenido realmente nuevo son los que se
   describen en `docs/prompt-implementacion-release-gate.md` y en tu propio resumen de
   cierre: `app/models.py`, `app/schemas/policy.py`,
   `app/services/governance_service.py`, `app/routers/governance.py`,
   `app/routers/environments.py`, más los nuevos `tests/test_governance_gate.py`
   y la carpeta `docs/`.

## Lo que quiero que hagas, en este orden

**1. Verificá el estado real vos mismo.** No confíes en mi diagnóstico sin
chequearlo: `git status`, `git branch --show-current` (debería decir
`main`), `git log --oneline -5`, y `git diff --ignore-space-at-eol --stat`
para confirmar cuáles archivos tienen cambio real y cuáles son solo ruido de
fin de línea. Si algo no coincide con lo que describo acá, parate y avisame
antes de continuar.

**2. Confirmá que el repo está al día.** Corré `git fetch --all` y después
`git status -sb` contra `origin/main`. Si `main` está desalineado de
`origin/main` (alguien pusheó algo nuevo), avisame antes de crear la rama —
no hagas merge ni rebase por tu cuenta sin decírmelo primero.

**3. Aislá SOLO el cambio real del ruido de fin de línea.** El objetivo es
que el PR final muestre nada más que el release gate — no 55 archivos. Los
archivos con ruido de CRLF que no están en la lista de arriba **no se tocan,
no se normalizan, no se commitean.** No hagas una normalización de fin de
línea del repo por tu cuenta: si son ~50 archivos afectados, probablemente
sea una diferencia de configuración de git de alguien del equipo (o mía), y
tocarlo sin avisar puede generar conflictos feos en las ramas de mis
compañeros (`gabriel-backend-rf17-rf18-rf19-rf20`, `modulo4-emilio`, etc.).
Encontrá la forma de armar un commit limpio que contenga únicamente el
contenido nuevo de esos 6-7 archivos, sin arrastrar el ruido de las líneas
que no cambiaron. Si no hay forma limpia de lograrlo (por ejemplo, porque el
archivo completo quedó guardado con otro fin de línea y no se puede separar
"tu cambio real" del "ruido" de forma confiable), decime exactamente por qué
y esperá instrucciones antes de commitear nada — no fuerces una solución
imperfecta.

**4. Creá la rama.** Nombre corto y en el estilo que ya usa el equipo (mirá
`git branch -a`: `modulo2-backend-despliegue`,
`modulo2-unificacion-api-core`, etc.) — algo como
`modulo2-release-gate-governance`. Creala desde el `main` ya actualizado del
paso 2.

**5. Commit solo de lo real**, con mensaje claro (estilo de los commits
existentes: `feat(modulo2): ...` — mirá `git log` para el formato exacto que
usa el repo).

**6. Corré la suite completa de nuevo** ya parado en la rama nueva, después
de aislar el cambio, para confirmar que el aislamiento no rompió nada
(`pytest tests/ -v`). Si algo da rojo, no sigas: avisame.

**7. Push de la rama** (`git push -u origin <nombre-de-rama>`).

**8. Preparate para el PR**, pero antes de abrirlo verificá si hay `gh` CLI
autenticada disponible en esta máquina. Si la hay, generá el PR (título +
descripción breve con qué resuelve y qué decisiones se tomaron, referenciando
`docs/plan-mlops-release-gate.md`) pero **no lo abras sin mostrarme el
título y la descripción primero.** Si no hay `gh` disponible o no está
autenticada, no intentes ninguna otra forma de abrir el PR — dejame el link
de comparación de GitHub (`.../compare/main...<rama>`) y yo lo abro a mano.

## Regla de siempre

Si en cualquier paso algo no coincide con lo que te describo acá —el estado
del repo, los nombres de archivo, la convención de commits del equipo,
cualquier cosa— parate y preguntame. No asumas, no improvises una
interpretación silenciosa, y no toques nada fuera de lo que se pide en este
prompt (en especial: no normalices fin de línea del repo entero, no hagas
merge/rebase de `main` sin avisar, no abras el PR sin mostrarme el contenido
antes).
