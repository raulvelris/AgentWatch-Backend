Copiar todo el texto de abajo (desde "Contexto" hasta el final) y pegarlo
como prompt en Claude Code, con `AgentWatch-Backend` como directorio de
trabajo. Es la continuación de la tarea de rama/commit/push anterior.

---

## Contexto

El commit `50919d0` en la rama `modulo2-release-gate-governance` (ya
pusheada a `origin`) probablemente incluye un trailer
`Co-Authored-By: Claude ... <noreply@anthropic.com>` — así se definió en el
plan de la tarea anterior. Quiero sacar del proyecto toda mención a Claude o
Anthropic que quede como atribución/branding: en el mensaje de commit, en
comentarios o docstrings del código, y en nombres de archivo dentro de
`docs/`. Ya edité a mano `docs/plan-mlops-release-gate.md` (saqué la línea
"con apoyo de Claude"), así que no hace falta que toques ese archivo salvo
que encuentres algo que se me haya pasado.

Lo que SÍ dejo a propósito: las menciones a "Claude Code" dentro de los
prompts de `docs/` que son instrucciones dirigidas a la herramienta (por
ejemplo "pegar este texto en Claude Code") — esas no son atribución, son
parte funcional del documento. No las borres, solo evalúa los nombres de
archivo (ver paso 4).

## Qué hacer, en orden

1. **Verificá primero, no asumas.** Corré
   `git show -s --format="%B" HEAD` en esa rama para confirmar el trailer
   exacto que quedó en el commit real. Si no dice lo que describo acá,
   decime qué encontraste antes de seguir.

2. **Amend del commit**: mismo mensaje principal (el `feat(modulo2): ...`
   con su body), pero sin el trailer `Co-Authored-By` ni ninguna otra línea
   que mencione Claude o Anthropic.

3. **Grep de todo lo que entró en el commit** (los 5 `.py` del gate +
   `docs/` + el test nuevo) buscando `claude`/`anthropic`, case-insensitive.
   Si aparece en un comentario o docstring de código Python, sacalo también
   y sumalo al mismo commit (amend de nuevo, no un commit aparte).

4. **Renombrá con `git mv`** (para que quede como rename en el historial,
   no un delete+create):
   - `docs/prompt-claude-code.md` → `docs/prompt-implementacion-release-gate.md`
   - `docs/prompt-claude-code-branch-pr.md` → `docs/prompt-branch-pr.md`

   Actualizá la única referencia cruzada al nombre viejo (dentro de
   `prompt-branch-pr.md` ya renombrado, la línea "Es la continuación de
   `docs/prompt-claude-code.md`") para que apunte al nombre nuevo. Sumalo
   al mismo commit amendeado — quiero un solo commit limpio, no varios
   parches sueltos.

5. **Mostrame el mensaje final** (`git show -s --format="%B" HEAD`) y
   confirmame, con el mismo grep del paso 3 corrido de nuevo sobre el
   commit ya amendeado, que no queda "claude" ni "anthropic" en ningún
   lado salvo las menciones funcionales que dejamos a propósito (ver
   Contexto).

6. **Suite completa de nuevo** (`pytest tests/ -v`). El amend/rename no
   debería tocar lógica, pero confirmalo igual — no me entregues esto sin
   correrlo.

7. **Push.** La rama ya está en el remoto con el commit viejo, así que hace
   falta reemplazarlo: `git push --force-with-lease` (nunca `--force` a
   secas). Antes de pushear, corré `git status -sb` y confirmá que nadie
   más tocó esa rama en el remoto desde el último push — si `--force-with-lease`
   lo rechaza por eso, PARÁ y avisame, no reintentes con `--force`.

8. **Cerrá con:** el mensaje de commit final completo, confirmación de que
   el grep dio limpio, resultado de la suite, y confirmación de que el push
   salió bien.

## Regla de siempre

Si el trailer real no es el que describo, si el grep encuentra algo en un
lugar que no esperás, o si el push con `--force-with-lease` se rechaza
porque el remoto cambió, PARÁ y preguntame directamente. No asumas, no
fuerces nada a ciegas, y no toques ningún archivo fuera de lo que se pide
acá.
