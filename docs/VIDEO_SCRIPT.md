# Guion de video: Hornero de cero a producción

Duración sugerida: 25–35 minutos. Formato: captura de terminal + editor +
navegador mostrando reportes HTML. El presentador debe ejecutar los comandos en
un repositorio demo limpio y dejar visible el prompt completo.

## Preparación de la grabación

Crear un entorno con Python 3.11+, Git y, opcionalmente, Codex, Claude Code y
Gemini CLI. Aumentar la fuente de terminal y activar un tema con buen
contraste. Usar `examples/workflows/quickstart.sh` como ruta rápida, pero
mostrar también los comandos individuales en pantalla.

## Escena 1 — Qué problema resuelve (0:00–2:00)

Narración: “Hornero convierte señales de producto y código en un ciclo auditable:
inbox, evidencia, specs, aprobación humana, dispatch, memoria y reportes.”

Mostrar el diagrama del README y explicar que `.hornero/` es estado local,
`sdd/` es la fuente de verdad y `sdd/reports/` es la superficie de auditoría.

## Escena 2 — Instalar y crear el proyecto (2:00–5:00)

Ejecutar:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'hornero[knowledge]'
hornero blueprint list
hornero new demo-service --blueprint python-service --commit
cd demo-service
hornero status
```

En el editor mostrar `.hornero/config.yaml`, `sdd/specs/`, `sdd/tasks/` y
`.gitignore`. Explicar que la fábrica es reproducible y que los blueprints
pueden combinar componentes.

## Escena 3 — Adoptar un repo existente y sincronizar SDD (5:00–8:00)

Mostrar:

```bash
hornero init --hooks
hornero sdd status
hornero sdd diff .claude/commands/sdd-start.md
hornero sdd sync --dry-run
```

Narración: “La sincronización no pisa divergencias: obliga a elegir `--theirs`
o `--ours`.” Mostrar una resolución explícita como ejemplo.

## Escena 4 — De un documento a una spec aprobable (8:00–12:00)

Copiar un requisito de ejemplo al inbox y ejecutar:

```bash
hornero ingest requirements.md
hornero reconcile --dry-run
hornero reconcile
```

Pausar en la pantalla de evidencia. Explicar que el texto citado debe existir
literalmente en la señal y que sin aprobación no hay mutación.

## Escena 5 — Build, dispatch y flight recorder (12:00–15:00)

Ejecutar con backend determinista:

```bash
hornero build --backend mock
hornero runs list
hornero runs show RUN-REF
hornero scribe RUN-REF
```

Mostrar el trace y el Decision Record. Aclarar que `--backend cli` se reserva
para agentes configurados y autenticados por el usuario.

## Escena 6 — Memoria y consultas (15:00–19:00)

Ejecutar:

```bash
hornero reindex
hornero knowledge query "where is dispatch implemented?"
hornero knowledge page file:hornero/build.py
hornero knowledge related file:hornero/build.py
hornero knowledge impact requirement:SPEC-006 --depth 4
hornero validate --repair
```

Abrir `sdd/reports/knowledge-graph.html` y explicar la diferencia entre el
índice local de Hornero y el plano LLM-wiki opcional.

## Escena 7 — LLM-wiki y tres agentes (19:00–23:00)

Ejecutar:

```bash
hornero wiki parrot build
hornero wiki parrot query "how does dispatch select a backend?"
hornero wiki parrot export --output docs/wiki
hornero wiki codex install
hornero wiki claude install
hornero wiki gemini install
```

Mostrar los tres archivos de instrucciones y sus settings. Abrir cada agente y
formular la misma pregunta. Enseñar que todos empiezan por `wikitoolkit query`,
pero cada integración respeta el contrato nativo del producto.

## Escena 8 — Contratos, assurance y mejora continua (23:00–28:00)

Ejecutar:

```bash
hornero contracts generate
hornero contracts check
hornero improve scan
hornero improve plan --limit 10
hornero assurance threat-model
hornero assurance compliance iso27001
hornero report
```

Mostrar los HTML generados y explicar cómo una finding pasa por política,
aprobación y ledger antes de ser aplicada.

## Escena 9 — Runtime y workspace (28:00–31:00)

Ejecutar:

```bash
hornero runtime init
hornero runtime emit scan --risk low
hornero runtime tick
hornero runtime status --json
hornero workspace graph ../repos
```

Destacar que el runtime está deshabilitado por defecto y que el fanout
multi-repositorio está acotado y auditable.

## Escena 10 — Cierre y rutina diaria (31:00–33:00)

Ejecutar:

```bash
hornero status
hornero sdd status
hornero wiki parrot status
hornero validate
pytest -q
```

Narración final: “La rutina es consultar estado, revisar señales, aprobar
evidencia, despachar con el backend adecuado, reindexar y conservar los
reportes. Hornero no automatiza a ciegas: automatiza con límites, evidencia y
trazabilidad.”

## Recursos que deben aparecer en pantalla

- `README.md` para el mapa general.
- `docs/WORKFLOWS.md` como índice de comandos.
- `docs/USAGE.md` para el flujo operativo detallado.
- `docs/PARROT_WIKI.md` para el plano LLM-wiki.
- `sdd/reports/*.html` para resultados visuales.
