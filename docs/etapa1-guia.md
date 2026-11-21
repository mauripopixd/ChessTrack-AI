# Etapa 1 — Fundamentos + backend (17 cursos, 3 bloques)

**Bloque 0 — Setup (hecho):** repo, venv + python-chess, 5 PGN propios.

**Bloque 1 — Cimientos.** Cursos en orden: Fund. Ingeniería de Software; Pensamiento Lógico; Introducción a la IA; Git y GitHub (falta 72%); Python Intermedio; POO; Python Avanzado.
Construye: script que lea un PGN e imprima SAN, FEN tras cada jugada y resultado → módulo `pgn_parser` (`ParsedGame`, `ParsedMove`, `InvalidPGNError`); ramas por feature, PRs a tu repo.
Checkpoint: el parser lee los 5 PGN; PGN vacío o jugada ilegal lanza `InvalidPGNError`.

**Bloque 2 — Datos + API.** Cursos: Unit Testing; PostgreSQL (falta 30%); Fund. Bases de Datos; SQL y MySQL; FastAPI.
Construye, en orden: tests del parser (pytest: válida, ilegal, vacío, varias partidas, headers faltantes); modelos `users` (id, email único, username, hashed_password, created_at), `games` (id, user_id FK, pgn_raw, pgn_hash único por usuario, white, black, result, played_at, user_color, created_at), `moves` (id, game_id FK, ply, san, uci, fen_after; único (game_id, ply)); Alembic; auth Argon2 + JWT; endpoints `POST /auth/register`, `POST /auth/login`, `GET /users/me`, `POST /games` (varias partidas → resumen), `GET /games` (paginado, filtro resultado/fecha), `GET /games/{id}`, `GET /games/{id}/moves`, `DELETE /games/{id}`, `GET /health`; tests con TestClient y BD de prueba, incluido aislamiento entre usuarios.

**Bloque 3 — Ingeniería.** Cursos: Patrones de Diseño y SOLID; Estructuras de Datos Lineales; Complejidad Algorítmica.
Construye: aplicar lo visto (justificar paginación e índice `games(user_id, created_at)` con complejidad); README completo (instalación, variables de entorno, ejemplos curl).

**Criterios para pasar a Etapa 2 (todos):**
- Los 17 cursos marcados.
- Partida real subida por la API y recuperada con jugadas y FEN correctos.
- Jugada ilegal o PGN vacío → error 4xx claro, no 500.
- Tests pasan: parser, auth, CRUD, aislamiento entre usuarios.
- `alembic upgrade head` crea el esquema desde una BD vacía.
- Repo público, README, historial limpio, sin secretos.
- Sin mirar, explicar: transacción, para qué sirve un índice, qué hace `Depends`, diferencia 401 vs 403.

## Lecciones del Bloque 0
- curl a chess.com fue bloqueado por Cloudflare (guardó HTML): abrir siempre el PGN; uno válido empieza con `[Event`. Se descargó desde el navegador.
- `git add data/samples` (no `data`) para que `data/raw/` (ignorado) no entre.
- `scripts/pick_samples.py` lee `data/raw/...`, que no está en el repo: aclararlo en el README.
- Las 5 partidas de prueba (weytey): 1 blancas ganada mate; 2 negras perdida por abandono; 3 negras tablas por repetición; 4 blancas perdida por tiempo; 5 negras ganada por tiempo.
