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
- **Etapa 3** en `feat/stockfish-notebook`: Stockfish 19 instalado con winget (`%LOCALAPPDATA%\Microsoft\WinGet\Packages\Stockfish.Stockfish_*`; `find_stockfish()` lo encuentra). `app/analysis.py` (cp desde blancas, mates = ±10.000, cp_loss con tope de 1.000, probabilidad de ganar con la sigmoide de Lichess k=0.00368208, etiquetas por caída de probabilidad: imprecisión ≥5, error ≥10, error grave ≥20). `scripts/analyze_games.py` (ThreadPoolExecutor con un Stockfish por hilo; ProcessPoolExecutor + chess.engine se bloquea en Windows) → `data/analysis/moves.csv` (ignorado; 1.000 partidas = 75.251 jugadas a profundidad 12 en 240 s). `notebooks/01_stockfish_exploracion.ipynb` ejecutado y guardado con resultados. `requirements-analysis.txt`. En el CI se instala stockfish con apt (`/usr/games/stockfish`). 166 tests. Hallazgos para la Etapa 4: 82 % de jugadas buenas (desbalance), validar por partida, confusión por posiciones ya decididas.
- **Etapa 2, PR 3 (capas)**, mergeado (PR #9): `app/repositories/` (Protocol `UserRepository`/`GameRepository` + `Sql…Repository`; único sitio con SQL), `app/services/{auth,games}.py` como clases (`AuthService`, `GameService`) sin SQL ni HTTP, `app/errors.py` (errores de dominio), `deps.py` cablea sesión → repo → service. `tests/fakes.py` (repos en memoria), `tests/unit/` (22 tests sin BD, <1 s) y `tests/db/test_repository_contract.py` (mismas pruebas contra SQL y memoria). 153 tests. SOLID documentado en `docs/decisiones.md` §6. Con esto queda hecho todo lo que la Etapa 2 pide construir; faltan los cursos de la Etapa 2.
- **Etapa 2, PR 2 (Docker)**, mergeado (PR #8): `Dockerfile` (python:3.13-slim, deps antes que el código, usuario `app` uid 1000, HEALTHCHECK a /health; 272 MB), `.dockerignore` (sin .env/tests/scripts/data), `docker-compose.yml` con `db` → `migrate` (alembic upgrade head, one-shot) → `api` (puerto 8000; `JWT_SECRET_KEY` obligatoria vía `${...:?}` desde .env), `scripts/smoke_test.py` (flujo HTTP completo) y job `docker` en el CI. Checkpoint de la Etapa 2 cumplido en local: `docker compose down -v && docker compose up -d --build --wait` en 50 s. Sigue: capas routers/services/repositories (+ SOLID).
- **Etapa 2, PR 1 (CI)**, mergeado (PR #7): `.github/workflows/ci.yml` (jobs lint + test con servicio postgres:18; `alembic upgrade head`, `alembic check`, `pytest` con `REQUIRE_DB=1`, que convierte los skips de BD en fallos), ruff 0.17.6 (`[tool.ruff]` en pyproject, line-length 110) aplicado a todo el código, badge en el README.
- **Bloque 3**, mergeado (PR #6): `docs/decisiones.md` (mediciones EXPLAIN ANALYZE con 610.500 partidas: 6.105 reales de weytey + 99 usuarios sintéticos), migración `57ca8e8495e7` (índice `(user_id, created_at, id)`), arreglo de `list_games` (move_count solo para la página: 87 → 0,75 ms con offset 6000), `scripts/import_raw.py`, README con variables de entorno. Tras esto, para pasar a Etapa 2 solo faltan los cursos y las 4 preguntas teóricas (respuestas de apoyo en `docs/decisiones.md` §7).
- **Bloque 2, PR 3/3 (partidas)**, mergeado (PR #5): `POST /games` (multipart `file` + `player` opcional; importa partida a partida con `parse_pgn_each`, informa `created`/`duplicates`/`errors`; 201/200/422/413), `GET /games` (paginado + filtros result/fechas), `GET /games/{id}`, `GET /games/{id}/moves`, `DELETE /games/{id}`; lógica en `app/services/games.py`; ajena → 404. `eager_defaults` en User/Game y sesión de tests con `expire_on_commit=False` como la app. 121 tests. **Checkpoint de la Etapa 1 cumplido** (partida real subida por API y recuperada con jugadas y FEN).
- **Bloque 2, PR 2/3 (auth)**, mergeado (PR #4): FastAPI (`app/main.py`, `/health` con check de BD), `POST /auth/register` (409 por restricción de BD), `POST /auth/login` (form OAuth2; username o email; mismo mensaje y tiempo si no existe), `GET /users/me`; `app/security.py` (pwdlib Argon2id, PyJWT HS256, `algorithms` explícito), `app/deps.py` (`CurrentUser`, `SessionDep`), `app/schemas.py`. Email y username en minúsculas. `JWT_SECRET_KEY` en `.env` (mín. 32). Fixtures en `tests/conftest.py` (+ `client`); 80 tests. Avisos: httpx da un DeprecationWarning de Starlette (pide `httpx2`, no instalado); curl en Git Bash no codifica `ñ` en `-d`. Docker Desktop está en `%LOCALAPPDATA%\Programs\DockerDesktop` y hay que abrirlo antes de `docker compose`.
- **Bloque 2, PR 1/3 (modelos + Alembic)**, mergeado (PR #3): `app/config.py` (pydantic-settings, `.env`), `app/db.py` (Base con naming convention), `app/models.py` (users/games/moves), migración inicial escrita a mano, `docker-compose.yml` (postgres:18 en puerto 5433, BDs `chesstrack` y `chesstrack_test`), tests de BD en `tests/db/` (se saltan si no hay PostgreSQL). PostgreSQL nativo está desinstalado (solo queda `C:\Program Files\PostgreSQL\18\data`); se usa Docker Desktop. Ramas por feature y PRs. Cursos: Fund. Ingeniería de Software, Pensamiento Lógico, Intro a la IA, Git y GitHub (72% pendiente), Python Intermedio, POO, Python Avanzado.
- Platzi completado: Terminal, Fundamentos de Matemáticas, Cálculo Diferencial DS/IA, Estadística Descriptiva. En curso: Git y GitHub 28%, PostgreSQL 70%.

## Decisiones técnicas
- SQLAlchemy 2.0 + Alembic + schemas Pydantic separados (no SQLModel).
- Auth: Argon2 (pwdlib) + JWT; secretos en variables de entorno.
- python-chess: `read_game` devuelve None con texto vacío y no lanza ante jugadas ilegales (las deja en `game.errors`): revisar y lanzar `InvalidPGNError`.
- Guardar `fen_after` en `moves` desde ya (Etapa 4 lo usa con Stockfish).
- Costos: casi todo gratis; ~$10-20 USD de API LLM al final.
