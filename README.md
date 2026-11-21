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

Requisitos: Python 3.13 y Git. Comandos para CMD en Windows:

```bat
git clone <url-del-repo>
cd chesstrack-ai
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Estructura

```
data/
  samples/   partidas PGN de prueba (versionadas)
  raw/       exportaciones completas de chess.com (no versionadas)
docs/        plan del proyecto por etapas
```

## Licencia

MIT
