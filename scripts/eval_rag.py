"""Checkpoint de la Etapa 5A: 10 preguntas de teoría respondidas con fundamento real.

    python -m scripts.eval_rag                    # Groq (si hay clave) con respaldo en Ollama
    python -m scripts.eval_rag --provider ollama  # solo el modelo local

Por cada pregunta comprueba automáticamente:
- cita al menos una fuente,
- no cita números de fuente que no existen (invención),
- alguna de las fuentes que cita es de la apertura correcta (app/rag/eval_questions.py).
Escribe docs/rag_checkpoint_<proveedor>.md con las respuestas completas para leerlas.
"""

import argparse
import time
from pathlib import Path

import torch

from app.config import get_settings
from app.deps import build_llm_client
from app.rag.assistant import OpeningAssistant
from app.rag.eval_questions import CHECKPOINT, acierta
from app.rag.index import OpeningIndex
from app.rag.llm import LLMClient, LLMUnavailableError, groq, ollama

RAIZ = Path(__file__).resolve().parent.parent


def cliente(proveedor: str) -> LLMClient:
    s = get_settings()
    if proveedor == "groq":
        return LLMClient([groq(s.groq_api_key.get_secret_value(), s.groq_model)])
    if proveedor == "ollama":
        return LLMClient([ollama(s.ollama_model, s.ollama_url)])
    return build_llm_client()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--provider", choices=["auto", "groq", "ollama"], default="auto")
    args = parser.parse_args()

    s = get_settings()
    indice = OpeningIndex(Path(s.rag_index_dir), device="cuda" if torch.cuda.is_available() else "cpu")
    asistente = OpeningAssistant(indice, cliente(args.provider), k=s.rag_top_k)

    bloques, ok_total, latencias, modelos = [], 0, [], set()
    for i, p in enumerate(CHECKPOINT, start=1):
        # Groq gratis: 8.000 tokens/minuto y cada pregunta gasta ~3-4k. Si se agota, se espera
        # a que se renueve y se reintenta (en la API, en cambio, se pasa a Ollama al momento).
        for intento in range(4):
            try:
                inicio = time.perf_counter()
                a = asistente.ask(p.texto)
                break
            except LLMUnavailableError as e:
                if intento == 3:
                    raise
                print(f"   límite del proveedor ({e}); espero 35 s", flush=True)
                time.sleep(35)
        latencias.append(time.perf_counter() - inicio)
        modelos.add(f"{a.provider} · {a.model}")
        checks = {
            "cita fuentes": bool(a.citations),
            "sin citas inventadas": not a.invalid_citations,
            "cita la apertura correcta": any(acierta(c.moves, c.name, p) for c in a.citations),
        }
        ok = all(checks.values())
        ok_total += ok
        marcas = " · ".join(f"{'✅' if v else '❌'} {k}" for k, v in checks.items())
        fuentes = "\n".join(
            f"  - [{c.n}] [{c.title}]({c.url}) — {c.source}, {c.license}" for c in a.citations
        )
        bloques.append(
            f"### {i}. {p.texto}\n\n{a.text}\n\n{fuentes or '  - (sin citas)'}\n\n"
            f"{marcas} · {latencias[-1]:.1f} s · {a.provider}"
        )
        print(f"{'✅' if ok else '❌'} {i}. {p.texto} ({latencias[-1]:.1f} s, {a.provider})", flush=True)

    resumen = (
        f"{ok_total}/{len(CHECKPOINT)} preguntas superan las tres comprobaciones · "
        f"latencia mediana {sorted(latencias)[len(latencias) // 2]:.1f} s"
    )
    print(resumen)
    nombre = args.provider if args.provider != "auto" else "auto"
    (RAIZ / "docs" / f"rag_checkpoint_{nombre}.md").write_text(
        f"""# Checkpoint Etapa 5A · 10 preguntas de teoría con fuentes

> Generado por `python -m scripts.eval_rag --provider {args.provider}`. No editar a mano.

Modelo: {", ".join(sorted(modelos))}. Fuentes: Wikibooks *Chess Opening Theory* (CC BY-SA 4.0)
y Lichess *chess-openings* (CC0), recuperadas con `bge-m3` ({s.rag_top_k} fragmentos por pregunta).

**{resumen}**

Comprobaciones automáticas por respuesta: cita al menos una fuente · no cita números
inexistentes · alguna fuente citada es de la apertura preguntada. Leer las respuestas sigue
siendo necesario: las comprobaciones no verifican que cada frase diga lo mismo que su fuente.

{chr(10).join(bloques)}
""",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
