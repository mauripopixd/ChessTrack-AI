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

## Reproducir

```bat
python -m scripts.import_raw --user <tu-username>
docker compose exec db psql -U chesstrack -d chesstrack
```

Dentro de `psql`, antepón `EXPLAIN (ANALYZE, BUFFERS)` a las consultas de arriba.
