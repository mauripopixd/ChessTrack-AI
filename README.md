# ChessTrack AI

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

En construcción: **Etapa 1, capa 1 (backend)**. Hoja de ruta completa en [`docs/etapas.md`](docs/etapas.md).

## Instalación (desarrollo local)

Requisitos: Python 3.13, Git y Docker Desktop. Comandos para CMD en Windows:

```bat
git clone <url-del-repo>
cd chesstrack-ai
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d
alembic upgrade head
python -m pytest
uvicorn app.main:app --reload
```

Pega la clave que imprime el segundo comando en `JWT_SECRET_KEY` de `.env`. Con Docker Desktop abierto, `docker compose up -d` levanta PostgreSQL 18 en el puerto **5433** con dos bases: `chesstrack` (desarrollo) y `chesstrack_test` (los tests la vacían y la recrean con las migraciones en cada ejecución). Sin PostgreSQL, los tests de BD y de API se saltan con un aviso y el resto corre igual.

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
| `games` | id, user_id, pgn_raw, pgn_hash, white, black, result, played_at, user_color, created_at | (user_id, pgn_hash) único; result ∈ {1-0, 0-1, 1/2-1/2, \*}; user_color ∈ {white, black} o NULL; índice (user_id, created_at) |
| `moves` | id, game_id, ply, san, uci, fen_after | (game_id, ply) único; ply ≥ 1 |

Borrar un usuario borra sus partidas, y borrar una partida borra sus jugadas (`ON DELETE CASCADE`). Modelos en `app/models.py` (SQLAlchemy 2.0) y migraciones en `migrations/` (Alembic):

```bat
alembic upgrade head                           & rem aplica las migraciones pendientes
alembic revision --autogenerate -m "mensaje"   & rem crea una migración tras cambiar un modelo
alembic check                                  & rem falla si un modelo no tiene migración
```

## Parser de PGN

`app/pgn_parser.py` convierte texto PGN en objetos inmutables y valida lo que python-chess deja pasar en silencio:

```python
from app.pgn_parser import parse_pgn, parse_pgn_many, InvalidPGNError

game = parse_pgn(texto)          # exactamente una partida
game.white, game.black, game.result, game.played_at   # played_at en UTC
for m in game.moves:             # ParsedMove(ply, san, uci, fen_after)
    print(m.ply, m.san, m.fen_after)

games = parse_pgn_many(texto)    # varias partidas en un mismo texto
```

Lanza `InvalidPGNError` (con `game_index` si hay varias) ante texto vacío, texto que no es PGN, jugada ilegal o ambigua y resultado no válido. Para verlo en acción:

```bat
python -m scripts.print_pgn data\samples\partida1.pgn
```

Limitación conocida: python-chess ignora palabras sueltas dentro de las jugadas (`1. e4 hola e5` se lee como `1. e4 e5`).

## Datos

`scripts/download_games.py` baja las partidas de un usuario desde la [API pública de chess.com](https://www.chess.com/news/view/published-data-api) (sin login):

```bat
python scripts\download_games.py download             & rem todos los meses a data\raw\
python scripts\download_games.py download --months 1  & rem solo el último mes
python scripts\download_games.py list                 & rem tabla: color, resultado, final, jugadas especiales
python scripts\download_games.py pick 6018 6017 5883 6079 6068
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
  routers/        endpoints HTTP (auth, users, games)
  services/       lógica de negocio (importar y consultar partidas)
  deps.py         dependencias: sesión de BD, usuario autenticado
  security.py     Argon2 y JWT
  schemas.py      entrada/salida de la API (Pydantic)
  config.py       configuración desde variables de entorno / .env
  db.py           motor, sesiones y clase base de SQLAlchemy
  models.py       tablas users, games, moves
  pgn_parser.py   lectura y validación de PGN
migrations/       migraciones de Alembic
docker/           scripts de inicio de PostgreSQL
data/
  samples/        partidas PGN de prueba (versionadas)
  raw/            exportaciones completas de chess.com (no versionadas)
docs/             plan del proyecto por etapas
scripts/          utilidades (descarga de partidas, imprimir un PGN)
tests/            pytest
```

## Licencia

MIT
