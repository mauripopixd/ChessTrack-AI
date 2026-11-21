# ChessTrack AI — contexto para Claude Code

Coach de ajedrez con IA: se juega contra él, evalúa jugadas (buena/imprecisión/error) y explica el porqué en plena partida.

## Rol y forma de trabajo
**Claude construye el proyecto completo** (código, tests, configuración, docs) **bajo las indicaciones de Javier** (desde el 21 nov 2026; antes Javier escribía el código y Claude solo guiaba). Javier decide qué se hace y aprueba; Claude implementa. Contexto: es el proyecto de portafolio de Javier para perfilarse como **AI Engineer con base sólida de ML Engineer**, junto con la ruta de Platzi.
- Responde en español, directo y sin relleno.
- Antes de cada tarea grande, resume en pocas líneas qué vas a hacer; al terminar, explica brevemente qué se hizo y por qué, para que Javier pueda defenderlo en una entrevista.
- Commits, pushes y PRs solo cuando Javier lo pida.
- Antes de recomendar un curso de Platzi, verifica en platzi.com que exista con ese nombre exacto; si no lo confirmas, dilo.
- Prioriza construir el proyecto sobre coleccionar cursos: cada etapa termina con un entregable y un checkpoint.
- Sé honesto si algo del plan o del código está mal o es mejorable.
- Datos que cambian (salarios, precios, cursos): búscalos, no respondas de memoria.
## Usuario
Javier (Ingeniería de Sistemas, UNAD, Colombia). Meta: trabajo remoto para empresas de EE.UU./Europa.
Entorno: Windows, CMD (no PowerShell), Python 3.13, Git, GitHub `mauripopixd`, usuario chess.com `weytey`. Portátil MSI i7-13620H, 16 GB RAM, RTX 4070 8 GB.

## Sistema: 5 capas
1. Backend: FastAPI + PostgreSQL, PGN con python-chess, tests, Docker, CI (Etapas 1-2)
2. ML: clasificador de calidad de jugadas, etiquetas Stockfish; Random Forest → PyTorch (Etapa 4)
3. RAG de aperturas: sentence-transformers + Chroma/FAISS + LangChain (Etapa 5A)
4. Agente LangGraph: Stockfish + clasificador + RAG, trazas LangSmith (Etapa 5B)
5. Plataforma: AWS + Terraform + CI/CD + MLOps (Etapa 6)

Etapas: 1 Fundamentos+backend | 2 Arquitectura, Docker, CI | 3 Matemáticas | 4 ML | 5A RAG | 5B Agente | 6 Producción.
Detalle en `docs/etapas.md`, ruta de cursos en `docs/ruta-platzi.md`, Etapa 1 en `docs/etapa1-guia.md`.

## Estado actual (a 21 nov 2026)
- **Reinicio desde cero** en `C:\Users\mauri\Escritorio\chesstrack-ai`, única carpeta del proyecto. Repo: github.com/mauripopixd/ChessTrack-AI (público, recreado el 21 nov 2026; `origin`). GitHub CLI autenticado (`C:\Program Files\GitHub CLI\gh.exe`). Bloque 0 rehecho: README, .gitignore, LICENSE MIT, `.venv` con Python 3.13 (`py -3.13`; el `py` por defecto es 3.15), `requirements.txt` con `chess==1.11.2`, `scripts/download_games.py` (API pública de chess.com: `download` / `list` / `pick`). `data/raw/` tiene ~6.100 partidas de weytey (jul 2024 – oct 2026, todas estándar; no versionado, sirve para la Etapa 4). 5 muestras + `varias.pgn` en `data/samples/` (tabla en el README). Subcoronación y casos inválidos se cubrirán con PGN escritos a mano en los tests.
- Antecedente: hubo un primer intento (carpeta `proyectos\chesstrack-api` y repo `chesstrack-api`), ya eliminados por Javier. No queda nada de ahí.
- **Bloque 1 (código) hecho** en `feat/pgn-parser`: `app/pgn_parser.py` (`parse_pgn`, `parse_pgn_many`, `ParsedGame`, `ParsedMove`, `InvalidPGNError` con `game_index`), `scripts/print_pgn.py` (`python -m scripts.print_pgn <pgn>`), 31 tests en `tests/` (`python -m pytest`), `pyproject.toml` con config de pytest, `requirements-dev.txt` (pytest 9.2.0). Bloque 1 mergeado (PR #2).
- **Bloque 2, PR 1/3 (modelos + Alembic)** en `feat/db-models`: `app/config.py` (pydantic-settings, `.env`), `app/db.py` (Base con naming convention), `app/models.py` (users/games/moves), migración inicial escrita a mano, `docker-compose.yml` (postgres:18 en puerto 5433, BDs `chesstrack` y `chesstrack_test`), tests de BD en `tests/db/` (se saltan si no hay PostgreSQL). PostgreSQL nativo está desinstalado (solo queda `C:\Program Files\PostgreSQL\18\data`); se usa Docker Desktop. Siguen: PR 2/3 auth (Argon2 + JWT), PR 3/3 endpoints de partidas. Ramas por feature y PRs. Cursos: Fund. Ingeniería de Software, Pensamiento Lógico, Intro a la IA, Git y GitHub (72% pendiente), Python Intermedio, POO, Python Avanzado.
- Platzi completado: Terminal, Fundamentos de Matemáticas, Cálculo Diferencial DS/IA, Estadística Descriptiva. En curso: Git y GitHub 28%, PostgreSQL 70%.

## Decisiones técnicas
- SQLAlchemy 2.0 + Alembic + schemas Pydantic separados (no SQLModel).
- Auth: Argon2 (pwdlib) + JWT; secretos en variables de entorno.
- python-chess: `read_game` devuelve None con texto vacío y no lanza ante jugadas ilegales (las deja en `game.errors`): revisar y lanzar `InvalidPGNError`.
- Guardar `fen_after` en `moves` desde ya (Etapa 4 lo usa con Stockfish).
- Costos: casi todo gratis; ~$10-20 USD de API LLM al final.
