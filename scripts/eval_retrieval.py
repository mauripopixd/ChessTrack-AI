"""Mide la búsqueda del RAG: ¿la fuente correcta aparece entre los primeros resultados?

    python -m scripts.eval_retrieval

Para cada pregunta de app/rag/eval_questions.py busca los k fragmentos más parecidos y
mira en qué posición sale el primero de la apertura correcta. Métricas:
- acierto@k: proporción de preguntas con la fuente correcta entre los k primeros;
- MRR (rango recíproco medio): 1 si sale primera, 1/2 si segunda… premia el orden.
No llama a ningún LLM: es gratis y determinista. Escribe docs/rag_recuperacion.md.
"""

import argparse
import time
from pathlib import Path

import torch

from app.rag.eval_questions import PREGUNTAS, acierta
from app.rag.index import MODELO, OpeningIndex

RAIZ = Path(__file__).resolve().parent.parent
K = 5


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--index", type=Path, default=RAIZ / "data" / "vectorstore")
    parser.add_argument("--report", type=Path, default=RAIZ / "docs" / "rag_recuperacion.md")
    parser.add_argument("--model", default=MODELO, help=f"modelo de embeddings (por defecto {MODELO})")
    args = parser.parse_args()

    indice = OpeningIndex(
        args.index, modelo=args.model, device="cuda" if torch.cuda.is_available() else "cpu"
    )
    filas, rangos, tiempos = [], [], []
    for p in PREGUNTAS:
        inicio = time.perf_counter()
        hits = indice.search(p.texto, k=K)
        tiempos.append(time.perf_counter() - inicio)
        rango = next((i for i, h in enumerate(hits, start=1) if acierta(h.moves, h.name, p)), None)
        rangos.append(rango)
        primero = hits[0]
        filas.append(
            f"| {p.texto} | {rango or '✗'} | {primero.name or '—'} · `{primero.moves}` ({primero.source}) |"
        )
        print(f"{rango or '✗'}  {p.texto}  →  {primero.name} · {primero.moves}", flush=True)

    n = len(PREGUNTAS)
    acierto = {k: sum(r is not None and r <= k for r in rangos) / n for k in (1, 3, 5)}
    mrr = sum(1 / r for r in rangos if r) / n
    resumen = (
        f"acierto@1 {acierto[1]:.0%} · acierto@3 {acierto[3]:.0%} · acierto@5 {acierto[5]:.0%} · "
        f"MRR {mrr:.2f}"
    )
    print(resumen)
    args.report.write_text(
        f"""# RAG de aperturas · calidad de la búsqueda

> Generado por `python -m scripts.eval_retrieval`. No editar a mano.

Modelo de embeddings `{args.model}` (multilingüe), {n} preguntas en español sobre un corpus en
inglés. Un acierto es un fragmento de la apertura correcta (o de una variante suya) entre los
{K} primeros. Tiempo de búsqueda: mediana {sorted(tiempos)[n // 2] * 1000:.0f} ms por pregunta.

**{resumen}**

| Pregunta | Posición de la fuente correcta | Primer resultado |
|---|---|---|
{chr(10).join(filas)}
""",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
