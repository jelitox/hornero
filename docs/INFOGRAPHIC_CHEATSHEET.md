# Hornero: fuente para una infografía-cheatsheet

Este documento concentra el contenido y la dirección visual necesarios para
construir una infografía de referencia rápida de Hornero. No sustituye la guía
de uso: selecciona el recorrido principal, los comandos más útiles y los
límites de seguridad que deben poder leerse en pocos minutos.

## Evidencia del grafo

La selección se derivó del grafo local regenerado para esta rama antes de su
publicación:

| Señal | Valor |
| --- | ---: |
| Fuentes indexadas | 332 |
| Páginas | 383 |
| Relaciones | 686 |
| Entidades semánticas | 1.525 |
| Relaciones semánticas | 1.436 |
| Registros de procedencia | 2.994 |
| Specs representadas | 13 |

Consultas usadas para sintetizar esta pieza:

```bash
hornero knowledge query "main Hornero CLI commands and daily workflow"
hornero knowledge query \
  "safety invariants approval evidence dispatch and validation"
hornero knowledge query \
  "architecture governance advisory mockups parrot wiki workflows"
hornero knowledge coverage --json
```

Páginas principales recuperadas: `file:README.md`,
`file:docs/WORKFLOWS.md`, `file:docs/PARROT_WIKI.md`,
`file:docs/ARCHITECTURE_GOVERNANCE.md`, `file:hornero/cli.py` y las specs
`SPEC-001`, `SPEC-005`, `SPEC-006`, `SPEC-011`, `SPEC-012` y `SPEC-013`.

## Mensaje central

> Hornero convierte señales en software verificable mediante evidencia,
> aprobación humana, arquitectura reutilizable, ejecución registrada y memoria
> auditable.

Subtítulo corto para la pieza:

> De una necesidad a una entrega trazable, sin automatizar a ciegas.

## Composición visual recomendada

- Formato principal: vertical, 1440 × 2400 px.
- Variante de pantalla: 1920 × 1080 px en dos columnas.
- Fondo: terminal oscuro (`#11100E`).
- Color principal: arcilla Hornero (`#C86B3C`).
- Verificación y gates aprobados: verde (`#39B972`).
- Decisiones humanas: ámbar (`#F2B84B`).
- Riesgo, bloqueo o revisión requerida: rojo suave (`#E66A6A`).
- Texto: blanco cálido (`#F4EFE8`) y gris (`#AAA39A`).
- Tipografía: sans serif para títulos y monoespaciada para comandos.

La lectura debe seguir este orden:

1. Promesa del producto.
2. Flujo de extremo a extremo.
3. Cuatro reglas de seguridad.
4. Cheatsheet de comandos por intención.
5. Tres ejemplos copiables.
6. Rutina diaria y gates antes de mezclar.

## Flujo principal

Usar ocho nodos unidos de izquierda a derecha o de arriba hacia abajo:

```text
CREAR/ADOPTAR
     ↓
CAPTURAR SEÑALES
     ↓
RECONCILIAR + APROBAR
     ↓
VALIDAR ARQUITECTURA
     ↓
CONSTRUIR + DESPACHAR
     ↓
REGISTRAR DECISIONES
     ↓
INDEXAR + RECORDAR
     ↓
VALIDAR + MEJORAR
```

Versión con comandos:

```text
new / init
  → ingest
  → reconcile
  → spec preflight
  → build
  → runs + scribe
  → reindex + wiki parrot
  → validate + report + improve
```

### Texto corto para cada nodo

| Nodo | Texto para la infografía | Comando ancla |
| --- | --- | --- |
| Crear | Proyecto reproducible desde blueprint | `hornero new` |
| Adoptar | Añadir gobierno sin reemplazar el repo | `hornero init` |
| Capturar | Normalizar documentos con procedencia | `hornero ingest` |
| Reconciliar | Evidencia literal y aprobación humana | `hornero reconcile` |
| Arquitectura | Reutilizar capacidades antes de crear | `hornero spec preflight` |
| Construir | Spec aprobada → brief → backend | `hornero build` |
| Registrar | Trazas y Decision Records verificables | `hornero runs` / `scribe` |
| Recordar | Grafo local y memoria persistente | `reindex` / `wiki parrot` |
| Mejorar | Validación, reportes y cambios acotados | `validate` / `improve` |

## Cuatro reglas que deben quedar visibles

1. **Sin evidencia literal, no hay delta.** Las citas deben existir en la
   señal de origen.
2. **Sin aprobación, no hay mutación.** Los gates HITL fallan de forma cerrada.
3. **Sin backend explícito, no hay gasto sorpresa.** Usar `mock` para recorridos
   deterministas.
4. **Sin procedencia, no hay memoria confiable.** Specs, trazas, decisiones,
   reportes y recuerdos conservan origen e identidad.

## Cheatsheet por intención

### 1. Crear o adoptar

| Intención | Comando |
| --- | --- |
| Crear desde un blueprint | `hornero new APP --blueprint python-service --commit` |
| Inicializar un repo existente | `hornero init --hooks` |
| Ver salud general | `hornero status` |
| Ver blueprints | `hornero blueprint list` |
| Resolver capacidades | `hornero blueprint resolve api database auth` |

### 2. Gestionar SDD y requisitos

| Intención | Comando |
| --- | --- |
| Instalar toolkit | `hornero sdd install --from SRC` |
| Revisar drift | `hornero sdd status` |
| Ver una diferencia | `hornero sdd diff FILE` |
| Simular sincronización | `hornero sdd sync --dry-run` |
| Ingerir documentos | `hornero ingest FILE...` |
| Simular reconciliación | `hornero reconcile --dry-run` |
| Reconciliar con HITL | `hornero reconcile` |

### 3. Gobernar arquitectura

| Intención | Comando |
| --- | --- |
| Crear el corpus base | `hornero architecture init` |
| Inventariar evidencia | `hornero architecture inventory` |
| Consultar registros | `hornero architecture query "database"` |
| Resolver proveedores | `hornero architecture resolve database` |
| Validar una spec | `hornero spec preflight SPEC-013` |
| Ejecutar fitness checks | `hornero architecture check` |
| Comparar plan y realidad | `hornero architecture diff` |

### 4. Construir y auditar ejecuciones

| Intención | Comando |
| --- | --- |
| Build determinista | `hornero build SPEC-ID --backend mock` |
| Despachar al backend configurado | `hornero build SPEC-ID --backend cli` |
| Listar trazas | `hornero runs list` |
| Abrir una traza | `hornero runs show RUN-REF` |
| Crear un Decision Record | `hornero scribe RUN-REF` |

### 5. Consultar conocimiento

| Intención | Comando |
| --- | --- |
| Reconstruir índice local | `hornero reindex` |
| Buscar en el grafo | `hornero knowledge query "QUESTION"` |
| Abrir una página | `hornero knowledge page PAGE-ID` |
| Seguir relaciones | `hornero knowledge related PAGE-ID` |
| Medir impacto | `hornero knowledge impact ENTITY-ID --depth 4` |
| Explicar una entidad | `hornero knowledge explain ENTITY-ID` |
| Crear contexto acotado | `hornero knowledge context ENTITY-ID --budget 1200` |

### 6. Usar Parrot como wiki y memoria

| Intención | Comando |
| --- | --- |
| Construir LLM-wiki | `hornero wiki parrot build` |
| Consulta progresiva | `hornero wiki parrot query "QUESTION"` |
| Guardar una decisión | `hornero wiki parrot remember "FACT" --category decision` |
| Anotar una página | `hornero wiki parrot note PAGE-ID "NOTE"` |
| Conectar páginas | `hornero wiki parrot link SRC DST --rel REL` |
| Revisar recuerdos | `hornero wiki parrot memories` |
| Auditar escrituras | `hornero wiki parrot audit` |
| Verificar una afirmación | `hornero wiki parrot ground "CLAIM"` |
| Instalar un agente | `hornero wiki codex install` (también `claude` o `gemini`) |

### 7. Pedir perspectivas y crear mockups

| Intención | Comando |
| --- | --- |
| Revisión independiente | `hornero consult review --spec SPEC-ID --dry-run` |
| Brainstorm multiagente | `hornero consult brainstorm --spec SPEC-ID --dry-run` |
| Crear mockup trazable | `hornero mockup create --spec SPEC-ID --request TEXT --view home --dry-run` |
| Inspeccionar sesión | `hornero mockup show SESSION-ID` |
| Promover un artefacto | `hornero mockup promote RUN-ID ARTIFACT-ID --destination PATH` |

### 8. Operar y mejorar

| Intención | Comando |
| --- | --- |
| Validar trazabilidad | `hornero validate` |
| Regenerar reportes | `hornero report` |
| Buscar mejoras | `hornero improve scan` |
| Preparar un plan | `hornero improve plan --limit 20` |
| Modelo de amenazas | `hornero assurance threat-model` |
| Evidencia de cumplimiento | `hornero assurance compliance iso27001` |
| Emitir evento acotado | `hornero runtime emit scan --risk low` |
| Medir impacto entre repos | `hornero workspace graph ../repos` |

## Ejemplo 1: de requisito a build verificable

```bash
# 1. Incorporar la fuente
hornero ingest requirements.md

# 2. Revisar sin escribir
hornero reconcile --dry-run

# 3. Aprobar evidencia y crear/actualizar la spec
hornero reconcile

# 4. Comprobar reutilización y restricciones
hornero spec preflight SPEC-014

# 5. Ejecutar sin llamadas pagas
hornero build SPEC-014 --backend mock

# 6. Auditar la ejecución
hornero runs list
hornero runs show RUN-REF
hornero scribe RUN-REF
```

Resultado que debe mostrar la infografía:

```text
documento → evidencia → spec aprobada → preflight → build → trace → decisión
```

## Ejemplo 2: investigar y conservar conocimiento

```bash
# Recuperación progresiva
hornero wiki parrot query "how does dispatch select a backend?"
hornero wiki parrot page file:hornero/adapters/dispatch.py
hornero wiki parrot related file:hornero/adapters/dispatch.py

# Memoria persistente y atribuida
hornero wiki parrot remember \
  "Dispatch requires an approved build brief" \
  --title "Dispatch approval" \
  --category decision \
  --by codex

# Procedencia y grounding
hornero wiki parrot audit
hornero wiki parrot ground "Dispatch requires approval"
```

Resultado visual:

```text
pregunta → páginas → relaciones → decisión guardada → auditoría → grounding
```

## Ejemplo 3: revisión multiagente y mockup gobernado

```bash
# Obtener perspectivas sin mutar el repo
hornero consult review \
  --spec SPEC-012 \
  --providers codex,claude,gemini \
  --quorum 2 \
  --dry-run

# Diseñar una vista vinculada a la spec
hornero mockup create \
  --spec SPEC-012 \
  --request "dashboard de trazabilidad" \
  --from-scratch \
  --view overview \
  --dry-run
```

Resultado visual:

```text
spec → perspectivas independientes → findings → mockup → revisión → promoción
```

## Rutina diaria en siete comandos

```bash
hornero status
hornero sdd status
hornero reconcile --dry-run
hornero reindex
hornero wiki parrot status
hornero improve scan
hornero validate
```

## Gates antes de mezclar

```bash
pytest -q
ruff check .
mypy hornero
python scripts/changelog.py validate
```

Usar un cierre visual en verde:

> 371 tests · offline determinista · evidencia verificable · HITL fail-closed

## Etiquetas cortas e iconografía

| Concepto | Etiqueta | Icono sugerido |
| --- | --- | --- |
| Señal | entrada | bandeja |
| Evidencia | cita verificada | comillas + check |
| Spec | contrato | documento |
| Aprobación | decisión humana | mano/check ámbar |
| Arquitectura | reutilización | bloques conectados |
| Build | ejecución | martillo/engranaje |
| Trace | auditoría | ruta/pulso |
| Grafo | memoria | nodos conectados |
| Assurance | control | escudo |
| Runtime | automatización acotada | bucle con candado |

## Entregables derivados

Este Markdown puede alimentar:

- una infografía vertical para redes o documentación;
- una cheatsheet A4/PDF;
- una diapositiva 16:9 de onboarding;
- la actualización de `docs/artefacts/cheatsheet.es.html`;
- la actualización de `docs/artefacts/infographic.es.html`.

Al generar cualquier variante, conservar los comandos literalmente y reducir
primero el texto explicativo: nunca abreviar flags, ids o gates de seguridad.
