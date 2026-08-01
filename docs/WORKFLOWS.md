# Hornero: workflows reproducibles

Este documento es una guía práctica para recorrer Hornero desde cero. Cada
sección muestra el objetivo, los comandos y qué artefactos comprobar. Los
comandos que mutan el repositorio están marcados explícitamente; usa una copia
de prueba si estás aprendiendo.

## 0. Preparar el entorno

Hornero requiere Python 3.11 o superior. Para usar el plano LLM-wiki instala
el extra opcional `knowledge`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install 'hornero[knowledge]'
hornero --help
```

En desarrollo desde un checkout:

```bash
uv pip install -e '.[dev,knowledge]'
pytest -q
ruff check .
mypy hornero
```

## 1. Crear un proyecto bien configurado

La fábrica de proyectos genera Git, la configuración de Hornero, el layout
SDD y el blueprint seleccionado.

```bash
hornero blueprint list
hornero new billing-api --blueprint python-service --commit
cd billing-api
hornero blueprint status
hornero status
```

Para una selección explícita de capacidades:

```bash
hornero new billing-api \
  --blueprint python-service \
  --component docker \
  --component observability \
  --commit
hornero blueprint resolve api database auth observability
```

Comprobaciones iniciales:

```bash
git status --short
find .hornero sdd -maxdepth 2 -type f | sort
```

## 2. Inicializar un repositorio existente

`init` es idempotente y conserva la configuración existente.

```bash
cd ../mi-repo-existente
hornero init
hornero init --hooks
hornero status
```

El hook opcional ejecuta `hornero reindex` después de un merge. Para ver el
fragmento de CI sin escribir archivos:

```bash
hornero init --print-ci-hook
```

## 3. Instalar y sincronizar el toolkit SDD

```bash
hornero sdd install --from /ruta/al/sdd-toolkit
hornero sdd status
hornero sdd diff .claude/commands/sdd-start.md
hornero sdd sync --dry-run
hornero sdd sync
```

La sincronización es fail-closed: si un archivo está divergiendo, resuelve
explícitamente el lado ganador.

```bash
hornero sdd sync --theirs .claude/commands/sdd-task.md
hornero sdd sync --ours .claude/rules/python.md
hornero sdd sync --push .claude/commands/sdd-start.md
hornero sdd sync --workspace ../repos
```

## 4. Alimentar el inbox y reconciliar requisitos

```bash
hornero ingest requirements.docx architecture.html meeting.vtt
hornero status
hornero reconcile --dry-run
hornero reconcile
```

El modo `--dry-run` no escribe deltas. El modo interactivo presenta evidencia
verbatim y requiere aprobación humana antes de mutar specs.

## 5. Construir y despachar specs aprobadas

```bash
hornero build
hornero build SPEC-002
hornero build --backend mock
hornero runs list
hornero runs show RUN-REF
```

En un entorno con agentes CLI configurados, `--backend cli` usa el backend
seleccionado por la configuración. Para registrar un transcript existente:

```bash
hornero runs adopt ~/.claude/session.jsonl
hornero scribe RUN-REF
hornero runs prune --keep-days 90
```

## 6. Indexar y consultar conocimiento

```bash
hornero reindex
hornero knowledge query "where is dispatch implemented?"
hornero knowledge page file:hornero/build.py
hornero knowledge related file:hornero/build.py --rel references
hornero knowledge status
hornero validate --repair
```

Las consultas avanzadas navegan el grafo temporal y semántico:

```bash
hornero knowledge history requirement:SPEC-006
hornero knowledge analyze contradictions --json
hornero knowledge analyze duplicates --json
hornero knowledge impact requirement:SPEC-006 --depth 4
hornero knowledge coverage
hornero knowledge semantic-query --kind control --text security
hornero knowledge explain finding:FIND-ID
hornero knowledge context requirement:SPEC-006 --budget 1200
hornero extract requirements.md
```

## 7. Publicar el LLM-wiki para los agentes

```bash
hornero wiki parrot build
hornero wiki parrot status
hornero wiki parrot query "how does dispatch select a backend?"
hornero wiki parrot page file:hornero/adapters/dispatch.py
hornero wiki parrot related file:hornero/adapters/dispatch.py
hornero wiki parrot export --output docs/wiki
```

Instala la disciplina query-first en los agentes que uses:

```bash
hornero wiki codex install
hornero wiki claude install
hornero wiki gemini install
hornero wiki codex status --json
hornero wiki claude status --json
hornero wiki gemini status --json
```

Los tres pueden coexistir. Cada instalador preserva configuración de usuario,
es idempotente y mantiene `.parrot/` fuera de Git. Para retirar uno:

```bash
hornero wiki gemini uninstall
```

## 8. Informes, contratos y trazabilidad

```bash
hornero report
hornero report --only traceability
hornero contracts generate
hornero contracts check
```

Abrir los resultados en `sdd/reports/`: capacidades, workflows, trazabilidad,
grafo de conocimiento y contratos generados.

## 9. Mejora continua y políticas

```bash
hornero improve scan
hornero improve plan --limit 20
hornero improve status --json
hornero improve run --approve FIND-ID
hornero improve baseline FIND-ID --status accepted_risk \
  --reason 'legacy exception' --owner security@example.com --expires 2026-12-31
hornero improve baseline-status
```

## 10. Seguridad, assurance y runtime

```bash
hornero assurance supply-chain --feed offline-vulnerabilities.json
hornero assurance threat-model
hornero assurance compliance iso27001

hornero runtime init
hornero runtime emit scan --risk low
hornero runtime tick
hornero runtime approve EVENT-ID --by owner@example.com
hornero runtime feedback FIND-ID --helpful --notes 'verified fix'
hornero runtime status --json
```

El runtime permanece deshabilitado hasta que un responsable lo habilita. Los
eventos con aprobación requerida no se ejecutan por sorpresa.

## 11. Workspace multi-repositorio

```bash
hornero workspace graph ../repos
hornero workspace plan ../repos accounts/requirement:SPEC-101
```

Esto permite medir impacto entre repositorios sin copiar sus índices locales.

## 12. Flujo diario recomendado

```bash
hornero status
hornero sdd status
hornero reconcile --dry-run
hornero reindex
hornero wiki parrot status
hornero improve scan
hornero validate
hornero report
```

Antes de fusionar cambios, ejecutar los gates del proyecto:

```bash
pytest -q
ruff check .
mypy hornero
```

## 13. Diagnóstico rápido

| Síntoma | Comprobación | Acción |
| --- | --- | --- |
| No hay resultados de conocimiento | `hornero status` | `hornero reindex` |
| Wiki LLM no construida | `hornero wiki parrot status` | `hornero wiki parrot build` |
| Toolkit divergente | `hornero sdd status` | `--theirs` o `--ours` explícito |
| Reconcile no aplica | `hornero reconcile --dry-run` | revisar evidencia y aprobar |
| Hook no corre | revisar `.git/hooks/` | `hornero init --hooks` |
| Agente no consulta wiki | `hornero wiki <agente> status --json` | reinstalar y revisar hooks nativos |
