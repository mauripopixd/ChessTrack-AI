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
- **Etapa 4 (en curso):** clasificador de jugadas con Random Forest ([`docs/modelo_rf.md`](docs/modelo_rf.md)). Siguen una red en PyTorch y el endpoint que marca tus errores.

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
| `api` | La imagen del [`Dockerfile`](Dockerfile) (uvicorn, usuario sin privilegios, `HEALTHCHECK` contra `/health`) en http://127.0.0.1:8000 |

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
| `REQUIRE_DB` | no | — | `1` = los tests fallan (no se saltan) si no hay BD de pruebas. Lo usa el CI |

## API

Con `uvicorn` corriendo, la documentación interactiva está en http://127.0.0.1:8000/docs (el botón **Authorize** hace login y añade el token a las peticiones).

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
| DELETE | `/games/{id}` | Bearer | 204; borra también sus jugadas |

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

El Random Forest dobla a la regla manual y detecta el 59 % de los errores graves. Al pasar de 1.000 a 6.105 partidas apenas mejora (PR-AUC de 0,25 a 0,27): **el límite está en lo que ven las variables escritas a mano, no en la cantidad de datos.** Por eso el siguiente paso es una red en PyTorch que reciba el tablero completo.

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
  services/       lógica de negocio sin SQL ni HTTP (auth, games)
  repositories/   único sitio con SQL; interfaces (Protocol) + implementación SQLAlchemy
  errors.py       errores de dominio (duplicado, credenciales, subida simultánea)
  deps.py         cableado con Depends: sesión → repositorio → service; usuario autenticado
  security.py     Argon2 y JWT
  schemas.py      entrada/salida de la API (Pydantic)
  config.py       configuración desde variables de entorno / .env
  db.py           motor, sesiones y clase base de SQLAlchemy
  models.py       tablas users, games, moves
  pgn_parser.py   lectura y validación de PGN
  analysis.py     evaluación de jugadas con Stockfish
  ml/             variables del tablero para el clasificador
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
                  construir el dataset y entrenar el clasificador, imprimir un PGN, smoke test
tests/            pytest: parser, unitarios sin BD (tests/unit), BD y contrato (tests/db), API (tests/api)
.github/workflows/ CI de GitHub Actions
```

## Licencia

MIT
