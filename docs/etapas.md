# Etapas de ChessTrack AI

## Etapa 1 — Fundamentos + backend
Estudia: Fase 0 + Fase 1 + de Fase 2: FastAPI, PostgreSQL, Bases de Datos, SQL.
Construye: ChessTrack API (registro, subir PGN, parsear con python-chess, guardar en PostgreSQL, historial). Testing desde el día uno.
Checkpoint: subes una partida real vía API y la recuperas con sus movimientos correctos. Repo con README.

## Etapa 2 — Arquitectura sólida + termina el backend
Estudia: Arquitectura de Software Aplicada, SOLID, Docker Fundamentos, GitHub Actions.
Construye: capas routers/services/repositories, docker-compose (API + PostgreSQL), CI que corra tests en cada push.
Checkpoint: `docker-compose up` levanta todo desde cero; badge de CI pasa en el README.

## Etapa 3 — Matemáticas para ML
Estudia: Fase 3 completa (álgebra, álgebra lineal, cálculo, estadística descriptiva, probabilidad, inferencial).
Construye: explorar Stockfish en un notebook aparte (evaluaciones numéricas de posiciones).
Checkpoint: explicar con tus palabras qué es un intervalo de confianza.

## Etapa 4 — ML clásico + PyTorch
Estudia: Fase 4 (Python para Ciencia de Datos, Fund. ML, Regresión, Decision Trees/Random Forest, scikit-learn, PyTorch).
Construye: clasificador de calidad de jugadas (etiquetas Stockfish sobre partidas guardadas, features de posición, Random Forest y luego red en PyTorch). Endpoint que analiza una partida y marca errores.
Checkpoint: subes una partida real y el sistema marca tus errores, con métrica frente a Stockfish.

## Etapa 5A — RAG de aperturas
Estudia: Fundamentos de LLMs, Prompt Engineering, Config. APIs de LLMs, OpenAI API, Claude API, LangChain (+ Documentos), RAG con Azure.
Construye: teoría de aperturas indexada con embeddings; endpoint que responde citando fuente.
Checkpoint: 10 preguntas de teoría respondidas con fundamento real.

## Etapa 5B — Agente coach
Estudia: Herramientas de AI para Developers, LangGraph, MCP con Azure, LangSmith.
Construye: agente que combina Stockfish + clasificador + RAG para jugar y explicar cada jugada.
Checkpoint: partida completa con explicación bajo pedido y trazas en LangSmith.

## Etapa 6 — Producción
Estudia: Docker Avanzado, Terraform, AWS Cloud Practitioner + IAM + EC2, MLOps, Kubernetes (nociones).
Construye: todo dockerizado, Terraform, AWS, CI/CD completo, MLOps.
Checkpoint: URL pública donde cualquiera se registra y juega contra el coach.
