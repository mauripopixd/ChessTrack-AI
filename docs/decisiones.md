# Decisiones técnicas y rendimiento

Por qué el backend está hecho como está, con mediciones reales. Notación: **N** = partidas en
toda la tabla, **k** = partidas de un usuario, **p** = tamaño de página (`limit`).

## Cómo se midió

- PostgreSQL 18.7 en Docker, portátil i7-13620H. Base de desarrollo con:
  - las **6.105 partidas reales** de `weytey` (jul 2024 – oct 2026), importadas con
    `python -m scripts.import_raw --user weytey` (74 s, ninguna inválida), con sus 456.921 jugadas;
  - **99 usuarios sintéticos** con una copia de esas partidas cada uno (solo filas de `games`):
    **N = 610.500**, k = 6.105 por usuario.
- `EXPLAIN (ANALYZE, BUFFERS)` de cada consulta, **mediana de 5 ejecuciones** con caché caliente.
  Las variantes de índice se probaron dentro de `BEGIN … ROLLBACK`.
- Las cifras absolutas dependen de la máquina; lo que importa es cómo crecen.

## 1. Índice del listado: `(user_id, created_at, id)`

`GET /games` hace, en esencia:

```sql
SELECT … FROM games WHERE user_id = :u ORDER BY created_at DESC, id DESC LIMIT 20 OFFSET 0;
```

| Índice disponible | Plan | Filas leídas | ms |
|---|---|---|---|
| ninguno que empiece por `user_id` | Parallel Seq Scan + sort | 610.500 | **12,6** |
| solo `uq_games_user_id_pgn_hash` | Index Scan + sort de las k filas | 6.105 | 3,6 |
| `(user_id, created_at)` (versión anterior) | Index Scan Backward + Incremental Sort | 297 | 0,50 |
| **`(user_id, created_at, id)`** (actual) | Index Scan Backward, sin sort | **20** | **0,25** |

**Por qué funciona.** Un índice B-tree guarda las claves ordenadas. Con `user_id` primero, todas
las partidas de un usuario están juntas y ya ordenadas por `created_at` e `id`. PostgreSQL baja
por el árbol hasta el final del bloque de ese usuario, en O(log N), y lee hacia atrás solo las p
filas de la página: **O(log N + p)**. Sin índice tiene que mirar las N filas de la tabla, es decir
**O(N)**, y además ordenar.

- El orden de las columnas importa. Primero va la que se compara por igualdad (`user_id`) y después
  las del `ORDER BY`. Al revés, `(created_at, user_id)`, no serviría para "las de este usuario".
- **Por qué se añadió `id`** (migración `57ca8e8495e7`). Las partidas subidas en un mismo archivo
  comparten `created_at`, porque `now()` es la hora de inicio de la transacción. Con el índice
  anterior, PostgreSQL tenía que leer el grupo entero de la última subida (297 filas) y ordenarlo
  por `id` para quedarse con 20. Con `id` en el índice, el orden ya viene hecho.
- **Coste.** El índice ocupa 24 MB con 610.500 filas, frente a 102 MB de la tabla. Cada `INSERT` lo
  actualiza, en O(log N). Compensa porque se lee mucho más de lo que se escribe.
- Con 12,6 ms el barrido completo todavía parece rápido, pero crece con N: con 10 veces más
  usuarios tardaría unas 10 veces más. Con índice, el tiempo casi no cambia, porque log N crece muy
  despacio.

## 2. Paginación: `limit` + `offset`

**Por qué paginar.** Sin paginación, la respuesta crece con k: 6.105 partidas por petición, y
cientos de miles en el futuro. Con `limit` ≤ 100, cada respuesta tiene un tamaño acotado.

**El coste de `offset`.** `OFFSET n` no salta las filas: las lee y las descarta. Su coste es
**O(log N + n + p)**.

| Página | ms |
|---|---|
| `OFFSET 0` | 0,26 |
| `OFFSET 6000` (la última de weytey) | 0,75 |
| misma página con *keyset*: `WHERE (created_at, id) < (:c, :i)` | **0,02** |

La paginación por *keyset* (también llamada "por cursor") pide "las 20 anteriores a la última que
vi". Va directa a esa posición del índice, así que cuesta O(log N + p) en cualquier página.

**Decisión: `offset` por ahora.** Con k ≈ 6.000, la página más profunda tarda menos de 1 ms. Además,
`offset` permite saltar a la página 50 y mostrar el total, cosa que el *keyset* no hace. Se pasará a
*keyset* si aparece un *scroll* infinito o usuarios con cientos de miles de partidas. No hace falta
tocar el índice: ya sirve para las dos formas.

**`total`.** `SELECT count(*) … WHERE user_id = :u` recorre las k entradas del usuario en el índice
(Index Only Scan): **O(log N + k)**, 0,5 ms. Si llegara a pesar, se podría guardar el contador en la
tabla `users`.

## 3. Problema encontrado midiendo: `move_count` en páginas profundas

La primera versión calculaba `move_count` (una subconsulta que cuenta en `moves`) en la misma
consulta que el `OFFSET`. PostgreSQL evalúa las columnas del `SELECT` antes de descartar las filas
del offset, así que con `OFFSET 6000` contaba las jugadas de **6.020 partidas** para devolver 20:
**87 ms**.

Ahora se hace en dos pasos dentro de la misma consulta:
1. Una subconsulta elige los ids de la página usando solo el índice (Index Only Scan).
2. La consulta exterior une esos 20 ids con `games` y cuenta sus jugadas.

Resultado: **0,75 ms**, unas 115 veces menos. La regla general es no calcular nada caro antes de
paginar. Este fallo no aparece con 5 partidas en los tests; hace falta volumen real para verlo.

## 4. Otras consultas

| Consulta | Índice | Complejidad | ms |
|---|---|---|---|
| Jugadas de una partida (`GET /games/{id}/moves`) | `uq_moves_game_id_ply` | O(log M + plies) | 0,014 |
| Duplicados de 500 partidas al importar (`pgn_hash IN (…)`) | `uq_games_user_id_pgn_hash` | O(m · log N), en 1 consulta | 1,3 |

- La restricción `UNIQUE (game_id, ply)` crea un índice que, además de impedir plies repetidos, sirve
  para leer las jugadas ya ordenadas. Por eso no hace falta otro índice en `moves.game_id`.
- Al importar se comprueban todos los hashes con **una** consulta `IN`, en vez de m consultas (una
  por partida). Así se evita el problema "N+1": 900 viajes de ida y vuelta a la BD por archivo.

## 5. Decisiones de diseño

| Decisión | Por qué |
|---|---|
| Reglas en la BD (`UNIQUE`, `CHECK`, `FK … ON DELETE CASCADE`) | Ningún camino del código puede saltárselas. Los errores 409 salen del nombre de la restricción (`uq_users_email`), así que no hay carrera entre dos peticiones simultáneas |
| Naming convention en `Base.metadata` | Nombres de restricciones estables, para que Alembic genere migraciones deterministas y los errores sean legibles |
| SQLAlchemy y Pydantic por separado (no SQLModel) | La tabla y la API cambian por motivos distintos, y así nunca se expone `hashed_password` por error |
| Partida ajena → **404**, no 403 | Un 403 confirmaría que ese id existe. El cuerpo es idéntico al de una partida inexistente |
| Duplicados por SHA-256 del PGN **normalizado** | Re-subir el mismo archivo con otros saltos de línea no crea copias. El hash es por usuario: dos usuarios pueden tener la misma partida |
| Importar partida a partida (`parse_pgn_each`) | Una partida mala no invalida un archivo de 900 |
| Argon2id para contraseñas | Lento y con mucha memoria a propósito, lo que encarece los ataques con GPU. Es la recomendación de OWASP |
| JWT con `algorithms` fijo y `exp`/`sub` obligatorios | Bloquea `alg: none` y tokens que nunca caducan |
| Login con mismo mensaje y mismo coste exista o no el usuario | No revela quién está registrado |
| Tests contra PostgreSQL real, cada uno en una transacción que se deshace | SQLite no tiene los mismos tipos, restricciones ni planes. El rollback deja la BD limpia sin borrar nada a mano |
| `eager_defaults` + `expire_on_commit=False` (también en los tests) | `created_at` lo pone la BD y vuelve en el mismo `INSERT … RETURNING`. Los tests usan la misma configuración que la app, así detectan lo que fallaría en ella |

## 6. Arquitectura por capas (Etapa 2)

```
HTTP ──► routers/      traducen HTTP ↔ service: validan parámetros y convierten errores en 401/404/409/422
           │ Depends (deps.py cablea: sesión → repositorio SQL → service)
           ▼
         services/     lógica de negocio: importar, detectar duplicados y color, paginar. Sin SQL ni HTTP
           │ Protocol (UserRepository, GameRepository)
           ▼
         repositories/ el único sitio con SQL: consultas, índices, transacciones, errores de la BD
           ▼
         PostgreSQL
```

Reglas comprobables con `grep`: en `routers/` y `services/` no se importa `sqlalchemy`, y en
`services/` y `repositories/` no se importa `fastapi`. Los errores de negocio están en
`app/errors.py` (`DuplicateUserError`, `InvalidCredentialsError`, `ConcurrentImportError`). Los
services los lanzan y los routers los traducen a códigos HTTP.

### SOLID, donde aporta algo concreto

| Principio | Dónde | Qué se gana |
|---|---|---|
| **S** (una responsabilidad) | Cada capa cambia por un solo motivo: el router si cambia la API, el service si cambia la regla de negocio, el repositorio si cambia la consulta o el índice | La optimización de `list_page` (sección 3) no tocó el service ni el router |
| **O** (abierto/cerrado) | Para guardar partidas en otro sitio (caché, otra BD) basta con escribir otra clase que cumpla `GameRepository` | `GameService` no se modifica |
| **L** (sustitución de Liskov) | `InMemoryGameRepository` y `SqlGameRepository` son intercambiables | Lo garantiza `tests/db/test_repository_contract.py`: las mismas pruebas pasan con los dos |
| **I** (interfaces pequeñas) | `UserRepository` tiene 3 métodos y `GameRepository` 5: solo lo que usan los services | Un fake se escribe en pocas líneas |
| **D** (inversión de dependencias) | Los services dependen de un `Protocol`, no de SQLAlchemy. Solo `deps.py` elige la implementación | 22 tests unitarios de la lógica sin PostgreSQL, en menos de 1 s, y el mismo `GameService` sirve a la API y a `scripts/import_raw.py` |

### Lo que cuesta y lo que no se hizo

- **Más archivos e indirección.** Para una consulta hay que mirar router, service y repositorio.
  Compensa porque la lógica (duplicados, colores, aislamiento) ya es lo bastante grande para querer
  probarla aislada, y en las Etapas 4 y 5 el agente y el clasificador usarán los mismos services.
- **Los modelos de SQLAlchemy hacen de entidades de dominio.** Una arquitectura "pura" tendría clases
  de dominio aparte y un mapeo en cada repositorio. Aquí sería duplicar `Game` y `Move` sin ganar
  nada medible, así que no se hizo. Se revisará si el dominio crece (por ejemplo, con análisis de
  Stockfish).
- **Sin Unit of Work.** Cada método de repositorio que escribe hace su propio `commit()`. Basta
  mientras cada caso de uso escriba en un solo repositorio. Si alguno tuviera que escribir en dos a la
  vez y de forma atómica, haría falta un Unit of Work común.
- **Los services devuelven schemas de Pydantic** (`GamePage`, `ImportResult`). Es pragmático: son
  objetos de datos sin dependencias de HTTP, y evita otra capa de conversión.

## 7. Las cuatro preguntas del checkpoint, con ejemplos de este repo

- **Transacción:** un grupo de operaciones que se aplican todas o ninguna. Por ejemplo, `import_pgn`
  guarda N partidas y sus jugadas con un solo `commit()`: si algo falla, no queda una partida sin sus
  jugadas. Los tests abren una transacción por test y la deshacen al final (`tests/conftest.py`).
- **Índice:** una estructura ordenada (B-tree) aparte de la tabla, que permite encontrar filas en
  O(log N) en vez de recorrer N. A cambio ocupa espacio y encarece las escrituras. Ver la sección 1.
- **`Depends`:** la inyección de dependencias de FastAPI. El endpoint declara lo que necesita
  (`CurrentUser`, `SessionDep`) y FastAPI lo construye antes de llamarlo. Por eso en los tests se
  puede sustituir la sesión por la de prueba (`dependency_overrides`).
- **401 vs 403:** **401** significa "no sé quién eres" (falta el token o no es válido: `/users/me` sin
  token). **403** significa "sé quién eres, pero no puedes hacer esto". Aquí, para partidas ajenas, se
  responde 404 a propósito (ver la sección 5).

## 8. Etapa 4: por qué la red no supera al Random Forest

| Modelo (92.553 jugadas de prueba) | PR-AUC |
|---|---|
| Al azar | 0,10 |
| Regla manual | — (F1 0,16) |
| Random Forest, 28 variables | 0,266 |
| CNN, solo tablero | 0,195 |
| CNN, tablero + 28 variables | 0,267 |

**Qué se observa:**
- Pasar de 1.000 a 6.105 partidas apenas mueve el Random Forest (0,25 → 0,27).
- La CNN sola sobreajusta pronto: su mejor época es la 3, y después la pérdida de entrenamiento baja mientras la validación empeora.
- La híbrida aporta poco sobre las variables.

Tres modelos muy distintos se paran en el mismo techo, y eso apunta a la **tarea**, no al modelo:

1. **Sin búsqueda no se ven las tácticas.** Muchos errores solo se ven calculando 3-4 jugadas. Stockfish las calcula; un modelo que mira una sola posición no puede, por muchos parámetros que tenga.
2. **Las etiquetas tienen ruido:**
   - salen de profundidad 12;
   - dependen de un umbral fijo de probabilidad;
   - no marcan los regalos en posiciones ya decididas (notebook de la Etapa 3, §7).
   Parte de lo que el modelo "falla" son casos dudosos.
3. **Hay pocos datos para una CNN.** 290.000 jugadas, de las que solo unas 29.000 son errores, es poco para aprender patrones de ajedrez desde cero. Las redes de los motores se entrenan con cientos de millones de posiciones.

**Qué haría falta para subir el techo**, de más a menos prometedor:
- **Preentrenar con datos públicos masivos.** La base de datos de Lichess publica millones de partidas con evaluaciones de Stockfish ya incluidas (`[%eval]`), y con ellas la CNN aprendería ajedrez antes de especializarse en tus partidas.
- **Predecir la evaluación (regresión) en vez de una etiqueta binaria:** es una señal más rica y con menos ruido.
- **Aumentar los datos con la simetría izquierda-derecha del tablero** cuando no hay derechos de enroque.

**Decisión para el producto:** el coach no tiene que elegir. Stockfish da la etiqueta definitiva, y el clasificador sirve de filtro rápido y explicable. Las variables más importantes (pieza colgando, material, capturas del rival) dicen *por qué* una jugada huele a error, que es justo lo que el agente de la Etapa 5B necesita para explicarla.

## 9. Etapa 5A: búsqueda del RAG de aperturas

El corpus (Wikibooks, en inglés) y las preguntas (en español) están en idiomas distintos, así que los embeddings tienen que ser **multilingües**. Se compararon tres modelos con las mismas 20 preguntas (`scripts/eval_retrieval.py`), midiendo si la fuente correcta aparece entre los k primeros fragmentos:

| Modelo | Parámetros | acierto@1 | acierto@3 | acierto@5 | MRR | Búsqueda (GPU) |
|---|---|---|---|---|---|---|
| multilingual-e5-small | 118 M | **80 %** | 80 % | 80 % | 0,80 | 10 ms |
| multilingual-e5-base | 278 M | 60 % | 80 % | 80 % | 0,69 | 10 ms |
| **bge-m3** (elegido) | 568 M | 75 % | **90 %** | **95 %** | **0,83** | 17 ms |

- **Se elige bge-m3** porque en un RAG el LLM recibe varios fragmentos: lo que cuenta es que la fuente buena esté entre ellos (acierto@5), no que salga primera. Solo falla una pregunta, la del Gambito de Dama aceptado.
- **Más grande no siempre es mejor:** e5-base queda por debajo de e5-small. Sin medir se habría elegido mal.
- **Coste:** 2,3 GB de modelo e indexar 6.519 fragmentos en 2,5 min con GPU. En un servidor sin GPU las búsquedas serán más lentas; se tendrá en cuenta en la Etapa 6.

**Decisiones del corpus:**
- Cada fragmento lleva una cabecera con apertura, ECO y jugadas, porque los párrafos sueltos no dicen de qué apertura hablan.
- Se descartan los esbozos de menos de 200 caracteres y las secciones finales (tablas de jugadas y bibliografía).
- Los fragmentos tienen como mucho 1.200 caracteres y se cortan por párrafos.
- Las fichas de Lichess (CC0) cubren preguntas de nombres y jugadas. Wikibooks (CC BY-SA 4.0, que obliga a citar) cubre ideas y planes.

## 10. Etapa 5A: qué LLM responde, y gratis

**Requisito de Javier:** que no haya que pagar.
- La primera idea fue la API de Claude, que es de pago.
- La segunda, usar su suscripción de Claude ($20) o la de cada usuario (ChatGPT Plus, etc.). **No es posible:** los planes de consumo no incluyen acceso a la API, y Anthropic prohíbe desde 2026 usar el OAuth de Free/Pro/Max en aplicaciones de terceros o hacer de proxy para usuarios finales. Tampoco vale encadenar la app a Claude Code: es para el uso propio del suscriptor.

**Solución:** una capa de LLM independiente del proveedor sobre el formato *chat completions* de OpenAI, que hablan Groq, Ollama y Gemini. Va en cadena:

| Orden | Proveedor | Coste | Límites | Medido (10 preguntas) |
|---|---|---|---|---|
| 1 | Groq · `openai/gpt-oss-120b` | Gratis, sin tarjeta | ~8.000 tokens/min, 1.000 peticiones/día (cabeceras `x-ratelimit-*`) | 9/10 · 1,8 s |
| 2 | Ollama · Qwen 3.5 9B (local) | Gratis | Ninguno (GPU propia) | 9/10 · 22,9 s |

- **Si Groq devuelve 429 o falla, la API pasa al momento a Ollama** en vez de esperar. El script de evaluación, en cambio, espera a que se renueve el límite, para medir Groq solo.
- **Los dos modelos "piensan" antes de responder.** En Groq se limita (`reasoning_effort: low`). En Ollama se desactiva (`none`): con razonamiento, el modelo local gastaba los tokens en pensar y devolvía la respuesta vacía tras 30 s.
- **Sin RAG, el modelo local inventa:** dijo que la Siciliana es "1.d4 c5" y se sacó una "Defensa Centrosiciana". Con las fuentes numeradas y la regla de citar, las respuestas se pueden comprobar, y cuando no hay fuente el modelo lo dice.
- **Citas de cualquier modelo:** el LLM escribe `[n]` y el backend las convierte en título, URL y licencia. Las marcas que no existen se devuelven aparte (`invalid_citations`) como medida de invención.

**Probado y descartado, la reescritura de la consulta.** Consiste en que el LLM traduzca la pregunta a una búsqueda en inglés con nombres de apertura. Arregla "Gambito de Dama aceptado", pero rompe otras 4: por ejemplo, reescribe la India de Rey como "Queen's Indian". El acierto@5 baja del 95 % al 80 % (`scripts/eval_retrieval.py --rewrite`). Queda como opción desactivada.

**Pendiente:** un límite de preguntas por usuario. El de Groq es por organización, así que un solo usuario podría agotarlo para todos. También hay que llevar el modelo de embeddings y el índice al despliegue (Etapa 6).

## 11. Etapa 5B: el coach como agente LangGraph

**Qué hace el LLM y qué no.** Un turno es una jugada o una pregunta. Validar la jugada, que Stockfish responda y etiquetarla se hace con código normal: es exacto, tarda unos 0,3 s y no gasta el límite gratuito de Groq (~8.000 tokens/min). El LLM solo **explica**: cuando el usuario pregunta, o cuando comete un error o error grave, que el grafo comenta sin que se lo pidan. En la partida de ejemplo ([`docs/coach_partida_ejemplo.md`](coach_partida_ejemplo.md)), con 33 jugadas y 4 preguntas, hubo 37 turnos, trazados en LangSmith en un solo hilo y sin fallos. Solo 5 llamaron al LLM: el error grave y las 4 preguntas. Gastaron 17.000 tokens en total, con una mediana de 2,2 s por respuesta. En una partida anterior, una respuesta cayó a Ollama por el límite de Groq y respondió igual (23 s).

**Las herramientas leen la partida; el LLM no les pasa datos.** En la primera versión la herramienta de evaluar recibía una FEN, y gpt-oss la copió mal ("…b KQ? Wait"). Ahora ninguna herramienta tiene argumentos, salvo la consulta opcional de teoría. El modelo solo decide *qué* consultar; los datos salen del tablero.

**Medido: con las herramientas solas, el modelo seguía inventando.** Tres problemas, cada uno con su arreglo:

| Problema observado | Arreglo |
|---|---|
| Comentando 2.Nf3?, dijo que "la torre de a8 capturó con …exd5". La herramienta devolvía "deja colgando una peón (valor 1)", demasiado vago | Las herramientas describen cada jugada con casillas ("dxe4: peón de d5 captura peón en e4"), qué pieza queda colgando y dónde, y la refutación del rival |
| En el comentario automático el modelo podía no llamar a la herramienta | El análisis va ya dentro del mensaje, con la orden de usar solo esos datos. Además ahorra una llamada |
| A "¿voy ganando?" respondió con la evaluación de un mensaje anterior (−0,6) en vez de la actual (+0,2) | El estado de la partida va siempre en el mensaje de sistema: jugadas, última jugada descrita, evaluación actual y piezas en peligro. Unos 150 tokens, sin motor extra |
| A "¿cuál ha sido mi peor jugada?" dijo una jugada buena: ninguna herramienta daba el historial | Herramienta `mis_errores`, con las jugadas malas ordenadas por caída de probabilidad. En la partida siguiente acertó (22. Ba1) |
| gpt-oss a veces cita con su formato nativo, `【1†source】`, y la fuente no salía | Se normaliza a `[1]` antes de buscar las citas |
| (En la web, con Javier.) Preguntó si d5 era buen plan, y el modelo inventó "…Nxe5, …Nf3+", dijo "Ne2 protege el caballo de f3" (su caballo estaba en g3), habló de un peón en e5 y de "c3" que no existían y propuso 0‑0‑0 con el rey ya enrocado | Herramienta `evaluar_jugada(jugada)` para "¿y si juego X?": evalúa la jugada sin hacerla, con la respuesta del rival descrita casilla a casilla. El estado lleva la lista de piezas de cada bando y los enroques posibles. Las líneas de `evaluar_posicion` van descritas. Nueva regla: solo mencionar jugadas que vengan de las herramientas. Con diferencias de décimas se avisa de que la jugada es igual de válida, porque "la mejor" cambia de un análisis a otro. Con la misma pregunta, ahora responde que d5 es jugable, que …Nd4 ataca el caballo de f3 y que la posición sigue igualada, como dice Stockfish |
| (En la web, con Javier.) Tras 1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 dijo que con Bxc6 "ganas el caballo" y que "te quedas con peones doblados", al revés: es un cambio y los doblados son del negro. Leía "Bxc6: captura caballo" como una ganancia | Cada línea lleva su **balance**: cambio igualado, ganas o pierdes material, qué pierde cada bando, y quién queda con peones doblados nuevos, calculado sobre el tablero (`balance_linea`). Regla: una captura con recaptura es un cambio. Ahora responde "Cambias tu alfil por el caballo… el negro termina con peones doblados en la columna c… No ganas material neto" |

Con esto, los comentarios de errores salieron correctos en todas las pruebas. En las preguntas abiertas quedan imprecisiones de detalle: por ejemplo, llamó "de casillas negras" al alfil de casillas blancas. Es el límite de un modelo gratuito explicando ajedrez. Se mitiga con datos exactos, no se elimina. También falla nombrar la apertura cuando la búsqueda trae una variante parecida: en la partida de ejemplo, la llamó "Francesa, variante Nimzowitsch" citando la Variante del Avance.

**Etiquetas en posiciones ya decididas.** Las etiquetas miden la caída de la probabilidad de ganar (Etapa 3). Con la partida perdida, la probabilidad ya está cerca de 0 y casi nada la baja más. Por eso, regalar material en una posición perdida sale como "buena" y no se comenta. Es coherente con cómo se etiquetó el dataset, pero un coach humano lo señalaría. Queda como mejora: comentar también por pérdida de material.

**Corte de bucles.** Si el modelo pide herramientas más de 3 veces en un turno, el grafo le pide responder con lo que ya tiene, sin herramientas. Pasó en una prueba en que una herramienta respondía siempre lo mismo. `recursion_limit` (16) es la red de seguridad de LangGraph.

**`reasoning_effort: medium` en Groq** (en la Etapa 5A era `low`). Con `low` mezclaba más datos en las respuestas. Cada respuesta usa unos 1.000-2.000 tokens y tarda 1-5 s. *Sustituido después por qwen3.8-27b: ver más abajo.*

**Un verificador y otro modelo (tras probar Javier en la web).** Con datos exactos el modelo seguía rellenando con ajedrez inventado. En la partida de Javier dijo, a "¿c3 es correcta?":
- "b4 ataca tu alfil de b3": un peón en b4 ataca a3 y c3;
- "Ne2 protege c3": el caballo ya estaba en e2;
- "c3 abre la diagonal a2-g8", donde el alfil ya estaba.

Cuatro arreglos, medidos con sus tres preguntas reales:

1. **Más datos calculados.** Cada jugada descrita dice qué pieza rival ataca después ("b4: … ataca peón en c3"). `evaluar_jugada` dice qué casillas gana o pierde cada pieza con la jugada.
2. **Verificador** (nodo `verificar` del grafo, antes de responder). Comprueba con código:
   - las **jugadas de pieza** que menciona la respuesta: tienen que ser legales, ser la respuesta del rival o ser la jugada siguiente con *otra* pieza ("c3 y luego Bc2"), o venir en los datos;
   - los **hechos que contradicen los datos**: de quién son los peones doblados, o "ganas el caballo" cuando ninguna línea gana material.

   Si algo falla, el LLM reescribe la respuesta, y lo que se corrigió queda en la traza (`inventadas`, `contradicciones`). Solo cuesta una llamada extra cuando hay error.
3. **Herramienta obligatoria** en la primera llamada de cada pregunta (`tool_choice="required"`). A "¿qué plan me recomiendas?" respondía de memoria e inventaba ("a5 gana espacio en el flanco de rey").
4. **Otro modelo para el coach**: `qwen/qwen3.8-27b`, también gratis en Groq (`COACH_GROQ_MODEL`). En la pregunta de c3, gpt-oss-120b repitió "b4 ataca el alfil de b3" en 2 de 2 respuestas con `reasoning_effort` medio. Con alto acertó en eso, pero inventó otras jugadas ("h3" para negras) y tardó 6 s. qwen acertó en 2 de 2 en 1,5 s y se ciñe más a los datos. El RAG sigue con gpt-oss, que es con el que se midió. Groq cuenta el límite por modelo, así que no compiten.

| Pregunta de Javier | Antes | Después |
|---|---|---|
| ¿c3 es correcta? | "b4 ataca tu alfil de b3", "Ne2 protege c3" | "b4, atacando tu peón de c3": correcto |
| ¿Comer o retirar el alfil? (tras 3…a6) | "ganas el caballo", "te quedan peones doblados" | El verificador detectó "tus doblados" y el texto final dice "cambio igualado… peones doblados del rival" |
| ¿Qué plan me recomiendas? | Sin herramientas: "a5 gana espacio en el flanco de rey" | Usa Stockfish: axb5 (+0,1) o c3 (−0,2), con las evaluaciones reales |

**Lo que no se arregla.** Las frases de estrategia general ("refuerza el centro") no se pueden verificar con reglas, y a veces se escapa algún detalle. Cuando Groq se satura responde Ollama (Qwen 9B local), que inventa bastante más. Pasa con muchas preguntas seguidas; en uso normal no ocurre.

**Por qué LangGraph y no un bucle a mano.** El flujo tiene ramas (jugada/pregunta/ilegal/error) y un ciclo LLM ⇄ herramientas. LangGraph lo declara como grafo, `ToolNode` ejecuta las herramientas, y cada nodo aparece por separado en las trazas de LangSmith sin instrumentar nada. El grafo se compila por partida porque las herramientas cierran sobre ella. Compilarlo tarda milisegundos.

**Jugadas brillantes (!!).** Una jugada es brillante si cumple tres cosas, calculadas con Stockfish y el tablero (`es_brillante` en `app/analysis.py`):
1. Es la mejor o casi: la caída de probabilidad de ganar es de 2 puntos o menos.
2. Sacrifica material: deja en peligro una pieza de valor 3 o más que antes no lo estaba, y que vale más de lo que captura.
3. La posición sigue siendo buena (≥ 50 %).

Sin mate a la vista, tampoco cuenta si ya se ganaba de sobra (> 97 %), porque ahí entregar material no tiene mérito. Con mate a la vista sí: es el sacrificio de dama que lleva al mate. Ejemplo de test: el mate de la coz de Philidor (Qg8+!! Rxg8 Nf7#). Ahí el clasificador sin motor le da un 59 % de ser error, porque solo ve la dama colgando: es un buen ejemplo de por qué el clasificador ayuda pero no sustituye al motor.

**Tablas (Etapa 6).** Las decide el código con la evaluación de Stockfish, sin el LLM: son decisiones, no explicaciones, y así son exactas, inmediatas y gratis (`app/coach/game.py`).

- **Si las ofrece el usuario**, el coach acepta cuando va peor (≤ −1 peón desde su lado) o, desde la jugada 15, cuando la posición está igualada (≤ +0,3). Antes de la jugada 15 contesta que es pronto, y con ventaja sigue jugando. Siempre explica el motivo.
- **Él las ofrece** solo en posiciones muertas: desde la jugada 20, con las últimas 6 evaluaciones dentro de ±0,25, y como mucho una vez cada 10 jugadas. La oferta queda pendiente en la BD (`draw_offer`). Jugar una jugada la rechaza.
- **Las tablas acordadas** guardan `1/2-1/2` con `termination = "agreement"`. El tablero no sabe de acuerdos (python-chess no termina la partida), así que `CoachGame.terminada` combina las dos cosas.

**El coach por la API (PR 2).**

- **Jugadas en JSONB, no en una tabla.** `coach_games.moves` guarda la lista de informes (`MoveReport`) de la partida. Siempre se lee y se escribe entera con la partida y nunca se consulta jugada a jugada, así que una tabla aparte solo añadiría joins. Las partidas subidas por PGN (`games`/`moves`) sí van en tabla, porque allí se consulta y analiza cada jugada.
- **Un turno bloquea la fila** (`SELECT … FOR UPDATE`) hasta el commit. Si llegan dos jugadas a la vez para la misma partida, la segunda espera y luego ve la posición nueva; sin el bloqueo, las dos partirían de la misma posición y una borraría a la otra. El bloqueo dura lo que el turno, de 0,3 a 5 s, y solo afecta a esa partida.
- **Límite por usuario: 20 respuestas del LLM por hora** (`COACH_ANSWERS_PER_HOUR`), contadas entre todas sus partidas. El cupo gratuito de Groq (~8.000 tokens/min, 1.000 peticiones/día) es de la organización, no de cada usuario. Se cuenta en la BD (`coach_messages`, índice `(user_id, created_at)`), así que vale aunque haya varios procesos de la API. Al llegar al límite, `/ask` devuelve 429 con `Retry-After`; las jugadas siguen, sin comentario. Es una ventana deslizante de una hora: más simple que un *token bucket* y suficiente para este uso.
- **Si el LLM falla, la jugada no se pierde.** El nodo del LLM captura el error y el turno termina sin respuesta. En `/move`, la jugada se guarda y `note` explica por qué no hay comentario; en `/ask`, la API responde 503 y no guarda nada.
- **El RAG se carga la primera vez que el coach busca teoría**, no al arrancar ni en cada jugada: bge-m3 tarda unos segundos y ocupa ~2 GB. En la prueba real, la primera pregunta tardó 24,5 s por eso.

## 12. Etapa 6: cómo se despliega

**Lo que se hizo al final: el PC de Javier como servidor.** AWS rechazó la tarjeta en la verificación (el cobro temporal de 1 USD) y Azure for Students no aceptó la cuenta de la UNAD. La alternativa sin tarjeta fue servir la app desde el propio PC:

- **Docker Compose de producción** (`docker-compose.prod.yml`): BD y secretos propios. La API escucha solo en `127.0.0.1:8080` y la BD no tiene puerto hacia fuera.
- **Tailscale Funnel** publica ese puerto en `https://<equipo>.<tailnet>.ts.net`, con certificado automático, sin abrir puertos del router y sin mostrar la IP de casa. Es gratis en el plan personal, que no permite uso comercial; este es un proyecto de portafolio. Se compararon otras opciones:
  - *quick tunnel* de Cloudflare: la URL cambia en cada arranque;
  - túnel con nombre de Cloudflare: exige un dominio propio;
  - ngrok gratis: tiene un tope de conexiones.
- **Ventaja inesperada:** con 16 GB de RAM va el RAG bueno (bge-m3, 95 % de acierto@5), no el e5-small que hacía falta en una VM de 2 GB.
- **Inconvenientes asumidos:** la web solo responde con el PC encendido, y es un servicio de casa abierto a internet. Por eso:
  - la API corre en un contenedor sin root;
  - la BD no se expone;
  - hay límite de intentos de login (10 cada 5 min) y de registros (5 por hora) por IP, además del límite de respuestas del LLM por usuario.

  Los límites de login viven en memoria, porque la API es un solo proceso. Con varias réplicas irían a Redis o a la BD.
- **La IP del cliente para el límite.** Tailscale hace de proxy y rellena `X-Forwarded-For` con la IP de quien se conecta (comprobado con una petición desde el propio tailnet), y uvicorn la usa con `--proxy-headers`. La documentación de Tailscale no aclara qué pone para visitantes de Funnel: queda por confirmar con una visita desde fuera (los datos móviles de un teléfono) mirando la IP en los logs. Si pusiera siempre la misma IP, el límite sería global en vez de por persona.
- **Medido en el PC:** la API con el RAG (bge-m3 en CPU) usa 1,7 GB de RAM. La primera pregunta de teoría tarda unos 17 s (carga el modelo) y las siguientes, ~1 s. La imagen pesa 2,9 GB (PyTorch de CPU) frente a 880 MB sin RAG.
- **AWS con Terraform queda pendiente** para cuando el proyecto crezca y haya una tarjeta que funcione. El diseño de abajo sigue siendo el plan para entonces; la imagen de Docker es la misma.

**Plan original (pendiente):**

**Requisitos:** URL pública donde cualquiera se registra y juega (checkpoint), coste casi cero y Terraform en AWS.

**Dónde corre.** Una sola máquina EC2 **t4g.small** (ARM Graviton, 2 vCPU y 2 GB de RAM) con Docker Compose: API, PostgreSQL y un proxy con HTTPS. Las cuentas nuevas de AWS (desde julio de 2025) tienen un plan gratuito de 6 meses con 100-200 USD de créditos, y la t4g.small es de las instancias que entran en él. Fuera del plan cuesta unos 12 USD al mes.

Se descartó ECS Fargate + RDS: es más "de libro", pero cuesta 30-50 USD al mes (RDS, balanceador y NAT) para un proyecto con pocos usuarios. Compose en una máquina es suficiente y fácil de explicar. Pasar a ECS/RDS después solo cambiaría el Terraform, porque la imagen es la misma.

**RAG con un modelo pequeño en producción.** bge-m3 ocupa unos 2,3 GB y no cabe en 2 GB junto a PostgreSQL. En producción va `intfloat/multilingual-e5-small` (~0,5 GB), que acierta menos (80 % frente a 95 % de acierto@5, §9). El modelo es una variable (`RAG_EMBEDDING_MODEL`); el índice se construye con el mismo modelo, y Chroma guarda una colección por modelo.

**Interfaz web sin framework.** HTML, CSS y JavaScript sin dependencias (`app/web/`), servidos por la propia API en `/`. Hay una sola pieza que desplegar, sin build de Node ni CORS, y la página usa los mismos endpoints que cualquier cliente.

- **El texto del LLM nunca se trata como HTML.** Se inserta como texto y solo se reconstruyen las **negritas** con nodos; los enlaces de las fuentes solo se crean si la URL es `https://`.
- **Cabeceras de seguridad:** una `Content-Security-Policy` que solo deja cargar recursos del propio servidor (sin scripts en línea ni de terceros), `frame-ancestors 'none'` contra el *clickjacking* y `nosniff`. Van en la cabecera HTTP y no en un `<meta>`, porque `frame-ancestors` no funciona en `<meta>` (el navegador lo avisa).
- **Tablero:** las jugadas legales las da la API (`legal_moves`), no un motor de reglas en JavaScript. Así hay una sola fuente de verdad (python-chess) y la web no duplica las reglas del ajedrez (enroques, al paso, coronaciones). Cada jugada trae la posición que deja (`fen_after`); con eso la web anima la última jugada desde la anterior. La pieza se desliza y la capturada se desvanece, porque con un cambio instantáneo no se entendía qué había pasado. Se arrastra con eventos *pointer*, que valen igual para ratón y dedo. Para revisar la partida basta un clic en cualquier jugada de la lista, los botones ⏮ ◀ ▶ ⏭ o las flechas del teclado: se ve la posición de ese momento, usando el `fen_after` que ya trae cada jugada. Mientras se revisa no se puede mover, y jugar o preguntar devuelve a la posición actual. Al coronar, la web pregunta con qué pieza: muestra una columna con dama, torre, alfil y caballo sobre la casilla, y clic fuera o Escape cancela. Si alguien prefiere no ver animaciones (`prefers-reduced-motion`), las jugadas aparecen sin movimiento.
- **El token JWT se guarda en `localStorage`.** Es lo simple para una SPA sin servidor de sesiones. El riesgo es que un XSS lo lea; la CSP y no insertar HTML lo mitigan. La alternativa más robusta, una cookie `HttpOnly` con protección CSRF, queda anotada como mejora.

**Cuando se retome AWS:** el Terraform (EC2, IP fija, *security group*, S3 para el índice y el clasificador, alerta de presupuesto) y el CD (GitHub Actions construye la imagen ARM, la sube a GHCR y despliega por SSM con OIDC, sin claves de AWS guardadas en GitHub).

## 13. La fuerza del coach por ELO

Antes se elegía el "Skill Level" 0-20 de Stockfish, que no dice nada a quien juega en chess.com o
Lichess. Ahora se elige un ELO de 400 a 3100 (la API acepta hasta 3190):

- **Desde 1320**, Stockfish limita su fuerza él mismo con `UCI_LimitStrength` + `UCI_Elo`. Es su
  rango (igual en el 17.1 de producción y en el 19 local), calibrado por sus desarrolladores con
  partidas entre motores: es una escala de motores, no la de chess.com.
- **Por debajo de 1320** Stockfish no baja más, así que el coach evalúa todas sus jugadas legales a
  profundidad 6 y elige con probabilidad `exp(-pérdida / T)`. T va de 300 cp a 400 de ELO, donde a
  menudo cuelga piezas, a 60 cp a 1300, donde pierde algún peón y rara vez una pieza. La mejor
  jugada sigue siendo la más probable. **No está calibrado** contra jugadores reales: es una
  aproximación razonable, y el test solo comprueba que a menos ELO salen más jugadas peores.
- Las partidas viejas conservan su `level`. En la BD, `level` y `elo` admiten NULL, pero una
  restricción exige que al menos uno tenga valor. La revancha usa la misma fuerza que la partida.

## 14. Un tutor que habla al nivel del alumno

Caso real: un usuario que no sabía ajedrez no entendía «dxc4». Por eso, al crear la partida se
elige qué sabe el usuario (`knowledge`). Es independiente del ELO del coach: alguien que empieza
puede jugar contra 400 y alguien con experiencia también.

- **El LLM sigue escribiendo SAN y el código lo traduce después** (`app/coach/lenguaje.py`). Si
  se le pidiera al LLM que escribiera «el peón de d5 se come…», podría equivocarse de pieza o de
  casilla, que es justo el tipo de error que ya cometía. Además, el verificador del grafo
  necesita la SAN para comprobar las jugadas. La traducción usa python-chess sobre las
  posiciones de la partida: la actual, las anteriores (para «tu jugada Bc4») y las que deja cada
  jugada ya nombrada en la respuesta (para «si juegas exd5, responde Qxd5»). Si una jugada no
  encaja en ninguna, se traduce sin tablero («el caballo va a f3»).
- **Un peón que avanza («e4») se escribe igual que una casilla.** Solo se traduce si va después
  de una palabra de jugar («juega e4», «mejor era d4»), si lleva número o si forma parte de una
  línea. «La casilla e4» se queda como está. Es una heurística: preferí dejar a veces una jugada
  sin traducir antes que convertir una casilla en una jugada.
- **El prompt cambia por nivel**: con «none», sin jerga, una idea por respuesta, sin números de
  evaluación y como mucho 80 palabras. Con «basic», explicar cada término técnico la primera
  vez. Con «advanced», el prompt de siempre.
- **Web**: coordenadas en el borde del tablero (sin ellas, «la casilla c4» no sirve de nada) y,
  con «none», una lista de jugadas con símbolos («♘ g1→f3») y la descripción al pasar el ratón.

- **Sugerencias en el tablero.** Cuando el coach responde una pregunta en tu turno, el código
  busca en la respuesta las jugadas que puedes hacer ya (`jugadas_sugeridas`) y la web dibuja cada
  una con una flecha de un color, con una pieza fantasma que hace el recorrido. Hay etiquetas del
  mismo color bajo el mensaje, y al pulsarlas se repite la animación. No cuentan las desaconsejadas
  («Nxe5 pierde», «evita Ng5»), las de una línea («Nf3 Nc6 Bc4»: solo la primera), las numeradas
  (teoría) ni las casillas sueltas. Además de la SAN, reconoce las frases de `en_palabras`: en la
  prueba real el LLM copió el estilo de sus respuestas anteriores, ya traducidas, y escribió «el
  caballo de b1 va a c3». Solo en preguntas: el comentario de un error habla de la posición de
  antes y dibujaría jugadas que ya no tocan.
- **Nombre en cada casilla** («c4») con los niveles «none» y «basic»; con «advanced», solo las
  coordenadas del borde.

## Reproducir

```bat
python -m scripts.import_raw --user <tu-username>
docker compose exec db psql -U chesstrack -d chesstrack
```

Dentro de `psql`, antepón `EXPLAIN (ANALYZE, BUFFERS)` a las consultas de arriba.
