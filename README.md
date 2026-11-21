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
docker compose up -d
alembic upgrade head
python -m pytest
```

Con Docker Desktop abierto, `docker compose up -d` levanta PostgreSQL 18 en el puerto **5433** con dos bases: `chesstrack` (desarrollo) y `chesstrack_test` (los tests la vacían y la recrean con las migraciones en cada ejecución). Sin PostgreSQL, los tests de BD se saltan con un aviso y el resto corre igual.

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
