# ChessTrack AI

[![CI](https://github.com/mauripopixd/ChessTrack-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/mauripopixd/ChessTrack-AI/actions/workflows/ci.yml)

Coach de ajedrez con IA: juegas contra él, evalúa tus jugadas (buena, imprecisión, error) y te explica el porqué, incluso en medio de la partida.

## Visión: un sistema, cinco capas

| # | Capa | Qué hace | Tecnologías |
|---|------|----------|-------------|
| 1 | Backend | API que guarda partidas PGN, las valida y expone el historial | FastAPI, PostgreSQL, python-chess, pytest, Docker |
| 2 | ML | Clasificador de calidad de jugadas con etiquetas de Stockfish | scikit-learn (Random Forest), PyTorch |
| 3 | RAG | Base de conocimiento de aperturas que responde citando fuentes | sentence-transformers, Chroma/FAISS, LangChain |
| 4 | Agente | Coach que combina Stockfish, el clasificador y el RAG para jugar y explicar | LangGraph, LangSmith |
| 5 | Plataforma | Despliegue público con CI/CD y MLOps | AWS, Terraform, GitHub Actions |

## Estado

**Etapa 1 (capa 1, backend): código completo.** API con registro, login JWT, subida de partidas PGN, historial paginado y jugadas con su FEN, sobre PostgreSQL y con 121 tests. Ya se cumple el checkpoint: una partida real se sube por la API y se recupera con sus jugadas y FEN correctos.

- Decisiones técnicas y mediciones de rendimiento con 610.000 partidas: [`docs/decisiones.md`](docs/decisiones.md).
- Hoja de ruta completa: [`docs/etapas.md`](docs/etapas.md). **Etapa 2:** CI ✅, Docker ✅, arquitectura por capas ✅ ([`docs/decisiones.md` §6](docs/decisiones.md)).
- **Etapa 3:** exploración de Stockfish con 1.000 partidas reales en [`notebooks/01_stockfish_exploracion.ipynb`](notebooks/01_stockfish_exploracion.ipynb).
- **Etapa 5A:** RAG de teoría de aperturas con `POST /openings/ask`, que responde citando Wikibooks y Lichess con un LLM **gratuito**. Checkpoint: 9/10 preguntas con fundamento real ([`docs/rag_checkpoint_groq.md`](docs/rag_checkpoint_groq.md)).
- **Etapa 5B:** coach con **LangGraph** contra el que juegas en la terminal (`python -m scripts.coach_cli`) o por la API (`/coach/games`): Stockfish responde, tus errores se comentan solos y puedes preguntarle lo que quieras; usa el motor, el clasificador y el RAG como herramientas, con trazas en LangSmith.
- **Etapa 6:** interfaz web en `/`: te registras, juegas arrastrando las piezas (con las casillas posibles marcadas, la coronación a elegir, o escribiendo la jugada), ves deslizarse las jugadas del coach y sus capturas, y chateas con él. Publicada en internet **desde un PC propio** con Docker y Tailscale Funnel ([cómo](#publicarlo-desde-tu-pc-etapa-6)). AWS con Terraform queda para cuando el proyecto crezca.
- **Etapa 4:** clasificador de jugadas con Random Forest ([`docs/modelo_rf.md`](docs/modelo_rf.md)) y red en PyTorch ([`docs/modelo_nn.md`](docs/modelo_nn.md)), y `POST /games/{id}/analysis`, que marca tus errores con Stockfish. Checkpoint cumplido.

## Arrancar

Requisitos: Git y Docker Desktop (abierto). Para desarrollar, además, Python 3.13. Comandos para CMD en Windows.

### Opción A: todo con Docker (lo más rápido)

```bat
git clone https://github.com/mauripopixd/ChessTrack-AI.git
cd ChessTrack-AI
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d --build --wait
```

Pega la clave que imprime el comando `python -c ...` en `JWT_SECRET_KEY` de `.env`. Si no tienes Python, vale cualquier texto aleatorio de 32 caracteres o más. Si falta, Compose no arranca y lo avisa.

`docker compose up` levanta tres servicios en orden:

| Servicio | Qué hace |
|---|---|
| `db` | PostgreSQL 18, expuesto en el puerto **5433** de tu equipo, con datos en el volumen `pgdata` |
| `migrate` | Ejecuta `alembic upgrade head` y termina. La API no arranca hasta que acaba bien, así que nunca corre con un esquema viejo |
| `api` | La imagen del [`Dockerfile`](Dockerfile) (uvicorn, Stockfish, usuario sin privilegios, `HEALTHCHECK` contra `/health`) en http://127.0.0.1:8000. Monta `./models` en modo solo lectura para el clasificador |

`--wait` espera a que `api` esté *healthy*. Para comprobar todo el flujo por HTTP, ejecuta `python -m scripts.smoke_test` (necesita `httpx`). Crea un usuario `smoke_…` de prueba en cada ejecución. Para apagar: `docker compose down`, o `docker compose down -v` para borrar también los datos.

### Opción B: desarrollo local (con recarga automática)

```bat
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
docker compose up -d db
alembic upgrade head
python -m pytest
uvicorn app.main:app --reload
```

`python -m pytest tests/unit` prueba la lógica de negocio sin base de datos, con repositorios en memoria, en menos de un segundo.

Aquí solo la BD corre en Docker. `uvicorn --reload` reinicia la API al guardar un archivo. Si ya levantaste la opción A, para antes su API (`docker compose stop api`), porque las dos usan el puerto 8000. La BD de desarrollo es `chesstrack` y la de tests es `chesstrack_test` (los tests la vacían y la recrean con las migraciones en cada ejecución). Sin PostgreSQL, los tests de BD y de API se saltan con un aviso y el resto corre igual.

### Calidad de código y CI

```bat
ruff check .          & rem linter (errores, imports, estilo)
ruff format .         & rem formatea el código
```

Cada push a `main` y cada PR ejecutan [`.github/workflows/ci.yml`](.github/workflows/ci.yml), con tres jobs en paralelo:

- **Lint:** `ruff check` y `ruff format --check`.
- **Tests:** instala Stockfish, levanta un PostgreSQL 18 de servicio y ejecuta `alembic upgrade head` desde una BD vacía, `alembic check` (modelos = migraciones) y `pytest`.
- **Docker:** `docker compose up --build --wait` desde cero y `scripts/smoke_test.py` contra la API del contenedor (checkpoint de la Etapa 2).

En el CI se define `REQUIRE_DB=1`: si la BD no respondiera, los tests de BD y API **fallarían** en vez de saltarse, para que el CI no salga en verde sin haber probado nada.

### Variables de entorno

Se leen de `.env` (copia de [`.env.example`](.env.example); git lo ignora) o del entorno, que tiene prioridad.

| Variable | Obligatoria | Por defecto | Para qué |
|---|---|---|---|
| `DATABASE_URL` | sí | — | BD de la app. Con docker-compose: `postgresql+psycopg://chesstrack:chesstrack@127.0.0.1:5433/chesstrack` |
| `TEST_DATABASE_URL` | para los tests de BD/API | — | BD que los tests **borran y recrean**. Nunca la misma que `DATABASE_URL` |
| `JWT_SECRET_KEY` | sí | — | Firma de los tokens, mínimo 32 caracteres. Quien la tenga puede fabricar tokens de cualquier usuario |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `60` | Duración de los tokens |
| `STOCKFISH_PATH` | no | se busca en el PATH y donde lo deja `winget` | Ruta del ejecutable de Stockfish (solo para el análisis y sus tests) |
| `ANALYSIS_DEPTH` | no | `12` | Profundidad de Stockfish en `POST /games/{id}/analysis` |
| `ENGINE_POOL_SIZE` | no | `2` | Análisis simultáneos como máximo (un Stockfish por cada uno) |
| `CLASSIFIER_PATH` | no | `models/clasificador_rf.joblib` | Modelo del clasificador. Si no existe, el análisis va solo con Stockfish |
| `GROQ_API_KEY` | no | — | LLM gratuito del RAG y del coach (console.groq.com). Sin ella, solo Ollama |
| `COACH_GROQ_MODEL` | no | `qwen/qwen3.8-27b` | Modelo de Groq del coach (el RAG usa `GROQ_MODEL`, `openai/gpt-oss-120b`) |
| `OLLAMA_MODEL` | no | `qwen3.5:9b-q4_K_M` | Modelo local de respaldo (vacío = sin respaldo) |
| `LANGSMITH_TRACING` | no | — | `true` = trazar los turnos del coach en LangSmith |
| `LANGSMITH_API_KEY` | no | — | Clave gratuita de smith.langchain.com (plan Developer) |
| `LANGSMITH_PROJECT` | no | `default` | Proyecto de LangSmith donde van las trazas |
| `RAG_EMBEDDING_MODEL` | no | `BAAI/bge-m3` | Modelo de embeddings del índice (el mismo que en `build_rag_index --model`). En producción, `intfloat/multilingual-e5-small` |
| `COACH_ANSWERS_PER_HOUR` | no | `20` | Respuestas del LLM del coach por usuario y hora (el cupo gratuito de Groq es compartido) |
| `REQUIRE_DB` | no | — | `1` = los tests fallan (no se saltan) si no hay BD de pruebas. Lo usa el CI |

## API

Con `uvicorn` corriendo, la **interfaz web** está en http://127.0.0.1:8000/ y la documentación interactiva de la API en http://127.0.0.1:8000/docs (el botón **Authorize** hace login y añade el token a las peticiones).

| Método | Ruta | Auth | Respuesta |
|--------|------|------|-----------|
| GET | `/health` | — | 200 `{"status":"ok","database":"ok"}`; 503 si la BD no responde |
| POST | `/auth/register` | — | 201 usuario; 409 si el email o el username ya existen; 422 si los datos no son válidos |
| POST | `/auth/login` | — | 200 `{"access_token", "token_type", "expires_in"}`; 401 si las credenciales fallan |
| GET | `/users/me` | Bearer | 200 usuario; 401 sin token o con token inválido/caducado |
| POST | `/games` | Bearer | Sube un `.pgn` (multipart, campo `file`; opcional `player`). 201 con `created`, `duplicates` y `errors` por partida; 200 si todas ya existían; 422 si ninguna es válida o no es UTF-8; 413 si pasa de 5 MB |
| GET | `/games` | Bearer | Paginado (`limit` 1-100, `offset`), filtros `result`, `played_from`, `played_to` (días UTC, inclusivos). Más reciente primero |
| GET | `/games/{id}` | Bearer | Partida con su PGN; 404 si no existe o es de otro usuario |
| GET | `/games/{id}/moves` | Bearer | Jugadas en orden: `ply`, `san`, `uci`, `fen_after` |
| DELETE | `/games/{id}` | Bearer | 204; borra también sus jugadas y su análisis |
| POST | `/games/{id}/analysis` | Bearer | Analiza con Stockfish (y el clasificador, si hay modelo) y guarda el resultado: cada jugada con evaluación, etiqueta y mejor jugada, tus errores y la comparación modelo/Stockfish. Tarda de 2 a 4 s por partida; si ya estaba analizada responde al instante (`?force=true` la rehace). 503 si no hay Stockfish |
| GET | `/games/{id}/analysis` | Bearer | El análisis guardado; 404 si aún no se ha analizado |
| POST | `/openings/ask` | Bearer | Pregunta de teoría de aperturas respondida con citas (Etapa 5A). 503 sin índice o sin LLM |
| POST | `/coach/games` | Bearer | Nueva partida contra el coach (`color` white/black, `level` 0-20). 201; si juegas con negras, el coach ya ha movido |
| GET | `/coach/games` | Bearer | Tus partidas contra el coach, paginadas, más reciente primero |
| GET | `/coach/games/{id}` | Bearer | Posición (FEN), jugadas con su etiqueta y el chat |
| POST | `/coach/games/{id}/move` | Bearer | Tu jugada (SAN o UCI): se etiqueta, el coach responde y, si fue un error, te lo comenta. 422 si es ilegal; 409 si la partida terminó |
| POST | `/coach/games/{id}/ask` | Bearer | Pregunta al coach sobre la partida. 429 si agotaste tus respuestas de la hora; 503 si ningún LLM responde |
| DELETE | `/coach/games/{id}` | Bearer | 204; borra la partida y su chat |
| POST | `/coach/games/{id}/draw` | Bearer | Ofreces tablas (o aceptas las del coach). Responde si las acepta y por qué. 409 si la partida terminó |
| POST | `/coach/games/{id}/draw/decline` | Bearer | Rechazas la oferta de tablas del coach. 204 |
| POST | `/coach/games/{id}/resign` | Bearer | Te rindes: gana el coach (`termination: resignation`). 409 si ya terminó |

- Contraseñas con **Argon2id** (`pwdlib`), de 8 a 128 caracteres. Tokens **JWT HS256** firmados con `JWT_SECRET_KEY`, que caducan a los `ACCESS_TOKEN_EXPIRE_MINUTES` (60 por defecto).
- Email y username se guardan en minúsculas, así que `Ana` y `ana` son el mismo usuario. El login acepta el username o el email.
- El login falla con el mismo mensaje y en el mismo tiempo exista o no el usuario, para no revelar quién está registrado.
- **Cada usuario solo ve sus partidas.** Una partida ajena responde 404 (no 403), igual que una inexistente, para no confirmar que ese id existe.
- **Duplicados:** se reconocen por el SHA-256 del PGN normalizado por python-chess, así que volver a subir el mismo archivo (aunque cambien saltos de línea o espacios) no crea copias. Dos usuarios sí pueden tener la misma partida.
- **Color:** `user_color` se deduce comparando `White`/`Black` con `player` o, si no se envía, con tu username. Si en chess.com te llamas distinto que en la app, envía `player`.

Ejemplo con curl (en CMD):

```bat
curl -X POST http://127.0.0.1:8000/auth/register -H "Content-Type: application/json" -d "{\"email\":\"yo@example.com\",\"username\":\"yo\",\"password\":\"password-larga\"}"
curl -X POST http://127.0.0.1:8000/auth/login -d "username=yo&password=password-larga"
curl http://127.0.0.1:8000/users/me -H "Authorization: Bearer <access_token>"
curl -X POST http://127.0.0.1:8000/games -H "Authorization: Bearer <access_token>" -F "file=@data/samples/varias.pgn" -F "player=weytey"
curl "http://127.0.0.1:8000/games?limit=10&result=1-0" -H "Authorization: Bearer <access_token>"
curl http://127.0.0.1:8000/games/1/moves -H "Authorization: Bearer <access_token>"
```

Si la contraseña lleva tildes o `ñ`, usa `--data-urlencode "password=..."` en vez de `-d`: curl no codifica esos caracteres en formularios.

## Base de datos

```
users  1 ── * games  1 ── * moves
```

| Tabla | Columnas | Reglas en la BD |
|-------|----------|-----------------|
| `users` | id, email, username, hashed_password, created_at | email y username únicos |
| `games` | id, user_id, pgn_raw, pgn_hash, white, black, result, played_at, user_color, created_at | (user_id, pgn_hash) único; result ∈ {1-0, 0-1, 1/2-1/2, \*}; user_color ∈ {white, black} o NULL; índice (user_id, created_at, id) para el listado |
| `moves` | id, game_id, ply, san, uci, fen_after | (game_id, ply) único; ply ≥ 1 |

Borrar un usuario borra sus partidas, y borrar una partida borra sus jugadas (`ON DELETE CASCADE`). Por qué estos índices y cuánto rinden: [`docs/decisiones.md`](docs/decisiones.md). Modelos en `app/models.py` (SQLAlchemy 2.0) y migraciones en `migrations/` (Alembic):

```bat
alembic upgrade head                           & rem aplica las migraciones pendientes
alembic revision --autogenerate -m "mensaje"   & rem crea una migración tras cambiar un modelo
alembic check                                  & rem falla si un modelo no tiene migración
```

## Parser de PGN

`app/pgn_parser.py` convierte texto PGN en objetos inmutables y valida lo que python-chess deja pasar en silencio:

```python
from app.pgn_parser import parse_pgn, parse_pgn_many, InvalidPGNError

game = parse_pgn(texto)  # exactamente una partida
game.white, game.black, game.result, game.played_at  # played_at en UTC
for m in game.moves:  # ParsedMove(ply, san, uci, fen_after)
    print(m.ply, m.san, m.fen_after)

games = parse_pgn_many(texto)  # varias partidas en un mismo texto
```

Lanza `InvalidPGNError` (con `game_index` si hay varias) ante texto vacío, texto que no es PGN, jugada ilegal o ambigua y resultado no válido. Para verlo en acción:

```bat
python -m scripts.print_pgn data\samples\partida1.pgn
```

Limitación conocida: python-chess ignora palabras sueltas dentro de las jugadas (`1. e4 hola e5` se lee como `1. e4 e5`).

## Análisis con Stockfish (Etapa 3)

`app/analysis.py` evalúa cada jugada con [Stockfish](https://stockfishchess.org/). Compara la posición antes (con la mejor jugada posible) y después de la jugada real:

- **cp_loss:** centipeones que pierde quien mueve. Su media por partida es el ACPL.
- **Probabilidad de ganar** (0-100): una sigmoide sobre la evaluación. Perder 100 cp con la partida igualada pesa mucho más que perderlos ganando por +900.
- **Etiqueta** según la caída de esa probabilidad: `buena` (< 5 puntos), `imprecision` (≥ 5), `error` (≥ 10), `error_grave` (≥ 20).

```bat
winget install --id Stockfish.Stockfish
pip install -r requirements-analysis.txt
python -m scripts.analyze_games --games 1000 --depth 12
jupyter lab notebooks
```

`analyze_games` usa un motor por núcleo: 1.000 partidas (75.000 jugadas) tardan unos 4 minutos a profundidad 12. El resultado va a `data/analysis/moves.csv`, que no se versiona. El notebook está guardado con sus resultados, así que en GitHub se lee sin ejecutar nada.

Lo que encontró el notebook con mis partidas:
- La mediana de pérdida es de 12 cp por jugada, pero la media es de 61, porque la distribución tiene una cola muy larga.
- Cometo el triple de errores en el medio juego que en la apertura.
- En las derrotas mi ACPL es 29 cp mayor que en las victorias (IC 95 % por bootstrap: 25-33 cp).
- La presión de tiempo parece *reducir* los errores, pero es una variable de confusión: con menos de 10 s, la mitad de las posiciones ya están decididas.
- El 82 % de las jugadas son "buenas". Las clases están muy desbalanceadas, y eso hay que tenerlo en cuenta para el clasificador de la Etapa 4.

## Clasificador de jugadas (Etapa 4)

> **Checkpoint:** subes una partida, `POST /games/{id}/analysis` marca tus errores con la jugada que proponía Stockfish y compara con el clasificador:
>
> ```
> weytey vs BrayanSaRo (0-1), yo con blancas · ACPL 64,5
>    25.Nxg5   error grave  pierde 308 cp · mejor: Qa4
>    45.g7     error grave  pierde 468 cp · mejor: Rg1
>    … (6 errores en total)
>    clasificador: marca 23, Stockfish 6, coinciden 3 · precisión 0,13 · recall 0,5
> ```
>
> Stockfish da la etiqueta definitiva. El clasificador es un aviso rápido sin motor (ver abajo por qué no puede ser más preciso).

¿Es esta jugada un **error**? Se considera error lo que Stockfish etiqueta como *error* o *error grave*. El modelo lo predice **sin motor**: [`app/ml/features.py`](app/ml/features.py) calcula 28 variables solo con el tablero (material, piezas que quedan colgando, capturas, jaques, amenazas del rival, mate en 1 permitido, reloj y tiempo gastado). Si el modelo recibiera la evaluación de Stockfish, "acertaría" copiando la etiqueta.

```bat
python -m scripts.analyze_games --games 100000 --out data\analysis\moves_all.csv
python -m scripts.build_dataset --moves data\analysis\moves_all.csv --out data\analysis\dataset_all.csv
python -m scripts.train_classifier --dataset data\analysis\dataset_all.csv
```

El análisis de las 6.105 partidas (456.921 jugadas) tarda unos 25 minutos; construir el dataset, menos de 1, y entrenar, 1 más. El modelo se guarda en `models/` (no versionado) y el informe en [`docs/modelo_rf.md`](docs/modelo_rf.md).

**Cómo se evalúa:**
- Separando **por fecha y por partida**: entrena con las partidas antiguas y prueba con el 20 % más reciente.
- El umbral de decisión se elige sin mirar la prueba.
- Se compara con dos líneas base: decir siempre "buena" y una regla escrita a mano (pieza colgando o mate en 1).

| Modelo (prueba, 92.553 jugadas) | Precisión | Recall | F1 | PR-AUC |
|---|---|---|---|---|
| Siempre "buena" | 0 | 0 | 0 | — |
| Regla manual | 0,16 | 0,16 | 0,16 | — |
| **Random Forest** | **0,24** | **0,53** | **0,33** | **0,27** (al azar: 0,10) |

El Random Forest dobla a la regla manual y detecta el 59 % de los errores graves. Al pasar de 1.000 a 6.105 partidas apenas mejora (PR-AUC de 0,25 a 0,27): el límite no está en la cantidad de datos.

### Red neuronal (PyTorch)

Una CNN residual ([`app/ml/net.py`](app/ml/net.py)) recibe el tablero antes y después de la jugada como tensor 26 × 8 × 8 ([`app/ml/board_tensor.py`](app/ml/board_tensor.py)), siempre visto desde quien mueve. Se prueban dos variantes, con la misma división y las mismas jugadas de prueba que el Random Forest:

```bat
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cu132
python -m scripts.train_nn --dataset data\analysis\dataset_all.csv
```

| Modelo | F1 | PR-AUC | ROC-AUC |
|---|---|---|---|
| Random Forest | 0,326 | 0,266 | 0,771 |
| Red · solo tablero | 0,276 | 0,195 | 0,718 |
| Red · tablero + variables | **0,331** | **0,267** | **0,778** |

En una RTX 4070 tarda 1,5 minutos (5 s por época, con todo el dataset en la GPU). El resultado sale idéntico al repetir el entrenamiento. **La red no supera al Random Forest:** solo con el tablero sobreajusta, y la híbrida empata. Los dos modelos chocan con el mismo techo (PR-AUC de unos 0,27). El análisis de por qué y qué haría falta para superarlo está en [`docs/decisiones.md` §8](docs/decisiones.md).

## RAG de aperturas (Etapa 5A)

Teoría de aperturas indexada para responder preguntas **citando la fuente**:

| Fuente | Licencia | Qué aporta |
|---|---|---|
| [Wikibooks · Chess Opening Theory](https://en.wikibooks.org/wiki/Chess_Opening_Theory) (2.655 páginas) | CC BY-SA 4.0 (obliga a citar) | Ideas y planes por variante |
| [Lichess · chess-openings](https://github.com/lichess-org/chess-openings) (3.865 aperturas) | CC0 | Nombre, ECO y jugadas |

```bat
python -m scripts.download_openings   & rem corpus a data\openings\ (~2 min; respeta los límites de Wikibooks)
python -m scripts.build_rag_index     & rem 6.519 fragmentos → embeddings bge-m3 → Chroma en data\vectorstore\
python -m scripts.eval_retrieval      & rem mide la búsqueda con 20 preguntas en español
```

- **Troceo** ([`app/rag/corpus.py`](app/rag/corpus.py)): cada fragmento lleva una cabecera con apertura, ECO y jugadas, y se descartan esbozos, tablas y bibliografía.
- **Índice** ([`app/rag/index.py`](app/rag/index.py)): usa **BAAI/bge-m3**, multilingüe porque las preguntas van en español y el corpus está en inglés. Se eligió comparando tres modelos: la fuente correcta sale entre los 5 primeros en **19 de 20 preguntas** ([`docs/decisiones.md` §9](docs/decisiones.md)).

Los datos descargados y el índice no se versionan. El modelo (~2,3 GB) se descarga de Hugging Face la primera vez.

### Preguntar: `POST /openings/ask` (con sesión iniciada)

```bat
curl -X POST http://127.0.0.1:8000/openings/ask -H "Authorization: Bearer <access_token>" -H "Content-Type: application/json" -d "{\"question\": \"¿Por qué se juega 3...a6 en la Apertura Española?\"}"
```

La respuesta trae el texto con marcas `[n]` y la lista de citas, cada una con título, URL y licencia. También incluye qué modelo respondió y las marcas `[n]` que no corresponden a ninguna fuente, que serían una invención.

**LLM gratuito, sin suscripciones** ([`app/rag/llm.py`](app/rag/llm.py)):

1. **Groq** con `openai/gpt-oss-120b`: gratis con límites (~8.000 tokens/minuto, unas 2 preguntas/minuto) y sin tarjeta. Pon tu clave gratuita en `GROQ_API_KEY` en `.env`.
2. **Ollama** local (`qwen3.5:9b`): gratis y sin límites. Se usa automáticamente si no hay clave de Groq o si Groq devuelve 429 o falla.

Los planes de consumo (Claude Pro, ChatGPT Plus) no pueden usarse como backend de una app: no incluyen API, y Anthropic lo prohíbe expresamente desde 2026.

**Checkpoint de la Etapa 5A** (`python -m scripts.eval_rag --provider groq|ollama`), con las 10 preguntas de teoría:

| Modelo | Superan las 3 comprobaciones | Latencia mediana |
|---|---|---|
| Groq · gpt-oss-120b | **9/10** | **1,8 s** |
| Ollama · Qwen 3.5 9B (local) | 9/10 | 22,9 s |

Las comprobaciones son: cita fuentes, no inventa números de cita y cita la apertura correcta. En la pregunta que falla (Gambito de Dama aceptado) la búsqueda no encuentra la página, y **los dos modelos dicen que sus fuentes no la cubren en vez de inventar**. Respuestas completas en [`docs/rag_checkpoint_groq.md`](docs/rag_checkpoint_groq.md) y [`docs/rag_checkpoint_ollama.md`](docs/rag_checkpoint_ollama.md).

El endpoint necesita las dependencias de `requirements-rag.txt` y el índice construido. Sin ellos responde 503 con la explicación, como en la imagen de Docker por defecto. La de producción (`WITH_RAG=1`, ver [Publicarlo desde tu PC](#publicarlo-desde-tu-pc-etapa-6)) sí los incluye.

## Coach con agente (Etapa 5B)

Juegas contra Stockfish (a la fuerza que elijas) y un LLM gratuito te explica la partida.

```bat
python -m scripts.coach_cli                          & rem blancas, coach nivel 5
python -m scripts.coach_cli --color negras --nivel 10 --teoria
```

Escribe una jugada (`e4`, `Nf3`, `O-O` o `g1f3`) o una pregunta ("¿por qué fue un error?", "¿qué plan tengo?"). Comandos: `/tablero`, `/pgn`, `/salir`.

**Grafo** ([`app/coach/graph.py`](app/coach/graph.py)): cada turno es una jugada o una pregunta.

```
jugada   ─► jugada_usuario ─► jugada_coach ─┬─ si fue error ─► comentario ─► coach ⇄ herramientas
              (validar + etiquetar)  (Stockfish) └─ si no ─► fin (sin LLM)
pregunta ─► coach ⇄ herramientas ─► fin
```

- **Lo determinista no pasa por el LLM.** Validar la jugada, que responda Stockfish y etiquetarla es código normal: es exacto, tarda 0,3 s y no gasta el límite gratuito. El LLM solo entra para **explicar**: cuando preguntas o cuando cometes un error.
- **Herramientas** ([`app/coach/tools.py`](app/coach/tools.py)): `estado_partida`, `evaluar_posicion` (Stockfish, 3 mejores líneas), `analizar_mi_ultima_jugada` (calidad, qué dejaste colgando, la refutación y la probabilidad del clasificador de la Etapa 4), `explicar_jugada_del_coach` y `buscar_teoria` (RAG de la Etapa 5A, con citas `[n]` y enlace).
- **El LLM nunca pasa una FEN ni jugadas a las herramientas**: las herramientas leen la partida directamente. Así los datos son exactos ([`docs/decisiones.md` §11](docs/decisiones.md)).
- **LLM:** Groq (`gpt-oss-120b`) con respaldo automático en Ollama, como en la Etapa 5A ([`app/coach/session.py`](app/coach/session.py)).

**Trazas en LangSmith** (plan Developer gratuito: 5.000 trazas/mes, sin tarjeta). Añade a `.env` `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY` y `LANGSMITH_PROJECT=chesstrack-coach`. Cada turno es una traza con sus nodos, llamadas al LLM, herramientas y tokens. Todos los turnos de una partida comparten un `thread_id`, así que la partida se ve como un hilo.

**Por la API** ([`app/services/coach.py`](app/services/coach.py)): cada turno bloquea la fila de la partida (`SELECT … FOR UPDATE`), la reconstruye, ejecuta el grafo y guarda las jugadas y el chat. Dos peticiones a la vez sobre la misma partida van una detrás de otra. Cada usuario tiene `COACH_ANSWERS_PER_HOUR` respuestas del LLM por hora. Al llegar al límite, `/ask` da 429, y las jugadas siguen funcionando pero sin comentario (el campo `note` lo explica). Si el LLM falla, la jugada se guarda igual.

```bat
curl -X POST http://127.0.0.1:8000/coach/games -H "Authorization: Bearer <access_token>" -H "Content-Type: application/json" -d "{\"color\": \"white\", \"level\": 5}"
curl -X POST http://127.0.0.1:8000/coach/games/1/move -H "Authorization: Bearer <access_token>" -H "Content-Type: application/json" -d "{\"move\": \"e4\"}"
curl -X POST http://127.0.0.1:8000/coach/games/1/ask -H "Authorization: Bearer <access_token>" -H "Content-Type: application/json" -d "{\"question\": \"¿Qué plan tengo?\"}"
```

**Checkpoint de la Etapa 5B** (`python -m scripts.coach_demo --teoria`): una partida completa en la que el usuario es Stockfish a nivel 1, que comete errores de verdad, y hace preguntas en jugadas fijas. Transcripción en [`docs/coach_partida_ejemplo.md`](docs/coach_partida_ejemplo.md).

## Publicarlo desde tu PC (Etapa 6)

La app completa corre en Docker en tu equipo, y **Tailscale Funnel** la publica en una URL HTTPS fija (`https://<equipo>.<tailnet>.ts.net`) sin abrir puertos del router ni mostrar tu IP. Así va todo, RAG con bge-m3 incluido, porque el equipo tiene RAM de sobra (una VM gratuita de 1-2 GB no da para el RAG).

```bat
rem 1. Secretos de producción en .env: PROD_DB_PASSWORD y PROD_JWT_SECRET_KEY (ver .env.example)
rem 2. Construir y arrancar (BD propia, migraciones y API en 127.0.0.1:8080)
docker compose -f docker-compose.prod.yml -p chesstrack-prod up -d --build
rem 3. Publicar con HTTPS (Tailscale instalado y con sesión iniciada)
"C:\Program Files\Tailscale\tailscale.exe" funnel --bg 8080
rem    Ver la URL pública / dejar de publicar
"C:\Program Files\Tailscale\tailscale.exe" funnel status
"C:\Program Files\Tailscale\tailscale.exe" funnel --https=443 off
```

- [`docker-compose.prod.yml`](docker-compose.prod.yml): BD y secretos distintos de los de desarrollo, la API escucha solo en `127.0.0.1` y la BD no tiene puerto hacia fuera. Se reinicia sola si se cae o si reinicias Docker.
- La imagen se construye con `WITH_RAG=1` (PyTorch de CPU, sentence-transformers y Chroma) y usa el índice y el modelo ya descargados en tu equipo, montados en el contenedor.
- El LLM es Groq y, si falla, el Ollama de tu equipo (`host.docker.internal`).
- **Límites:** 10 logins cada 5 minutos y 5 registros por hora por IP (429 al pasarse), además de las respuestas del coach por usuario y hora.
- Mientras el PC esté apagado o Docker cerrado, la URL no responde.

## Datos

`scripts/download_games.py` baja las partidas de un usuario desde la [API pública de chess.com](https://www.chess.com/news/view/published-data-api) (sin login):

```bat
python scripts\download_games.py download             & rem todos los meses a data\raw\
python scripts\download_games.py download --months 1  & rem solo el último mes
python scripts\download_games.py list                 & rem tabla: color, resultado, final, jugadas especiales
python scripts\download_games.py pick 6018 6017 5883 6079 6068
```

Para cargar ese historial completo en tu BD de desarrollo, sin el límite de 5 MB de la API (el usuario tiene que existir; regístralo antes con `POST /auth/register`):

```bat
python -m scripts.import_raw --user <tu-username> --player <tu-usuario-de-chess.com>
```

`data/raw/` no se versiona: cualquiera lo regenera con `download`. Las muestras de `data/samples/` sí, porque son los fixtures de los tests:

| Archivo | Color | Resultado | Final | Cubre |
|---------|-------|-----------|-------|-------|
| `partida1.pgn` | blancas | 1-0 | jaque mate | enroque largo |
| `partida2.pgn` | negras | 1-0 | abandono | captura al paso |
| `partida3.pgn` | negras | ½-½ | triple repetición | tablas |
| `partida4.pgn` | blancas | 0-1 | tiempo | coronación, enroque largo |
| `partida5.pgn` | negras | 0-1 | tiempo | victoria con negras |
| `varias.pgn` | — | — | — | las 5 en un solo archivo |

## Estructura

```
app/
  main.py         app FastAPI y /health
  routers/        capa HTTP: traduce peticiones y errores (auth, users, games)
  services/       lógica de negocio sin SQL ni HTTP (auth, games, analysis, coach)
  repositories/   único sitio con SQL; interfaces (Protocol) + implementación SQLAlchemy
  errors.py       errores de dominio (duplicado, credenciales, subida simultánea)
  engine.py       pool de procesos de Stockfish para la API
  deps.py         cableado con Depends: sesión → repositorio → service; usuario autenticado
  security.py     Argon2 y JWT
  schemas.py      entrada/salida de la API (Pydantic)
  config.py       configuración desde variables de entorno / .env
  db.py           motor, sesiones y clase base de SQLAlchemy
  models.py       tablas users, games, moves
  pgn_parser.py   lectura y validación de PGN
  analysis.py     evaluación de jugadas con Stockfish
  ml/             clasificador: variables del tablero, tensor del tablero y red (PyTorch)
  rag/            RAG de aperturas: corpus, troceo, índice vectorial y preguntas de evaluación
  coach/          agente LangGraph: partida contra Stockfish, herramientas, grafo y turno
  web/            interfaz web (HTML, CSS y JS sin frameworks) que sirve la propia API en /
migrations/       migraciones de Alembic
Dockerfile        imagen de la API
docker-compose.yml  db + migrate + api
docker/           scripts de inicio de PostgreSQL
data/
  samples/        partidas PGN de prueba (versionadas)
  raw/            exportaciones completas de chess.com (no versionadas)
docs/             plan por etapas y decisiones técnicas
notebooks/        análisis exploratorio (Etapa 3)
scripts/          utilidades: descargar de chess.com, importar a la BD, analizar con Stockfish,
                  construir el dataset y entrenar los clasificadores, corpus e índice del RAG,
                  imprimir un PGN, smoke test, jugar contra el coach (coach_cli, coach_demo)
tests/            pytest: parser, unitarios sin BD (tests/unit), BD y contrato (tests/db), API (tests/api)
.github/workflows/ CI de GitHub Actions
```

## Licencia

MIT
