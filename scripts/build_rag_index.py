"""Construye el índice vectorial del RAG a partir del corpus descargado.

    python -m scripts.download_openings   # una vez: corpus a data/openings/
    python -m scripts.build_rag_index     # trocea, calcula embeddings e indexa en data/vectorstore/

La primera vez descarga el modelo de embeddings de Hugging Face (BAAI/bge-m3, ~2,3 GB).
"""

import argparse
import time
from collections import Counter
from pathlib import Path

import torch

from app.rag.corpus import build_chunks
from app.rag.index import MODELO, OpeningIndex

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--corpus", type=Path, default=RAIZ / "data" / "openings")
    parser.add_argument("--out", type=Path, default=RAIZ / "data" / "vectorstore")
    parser.add_argument("--model", default=MODELO, help=f"modelo de embeddings (por defecto {MODELO})")
    args = parser.parse_args()

    inicio = time.perf_counter()
    chunks = build_chunks(args.corpus)
    print(f"{len(chunks)} fragmentos: {dict(Counter(c.source for c in chunks))}", flush=True)
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    indice = OpeningIndex(args.out, modelo=args.model, device=dispositivo)
    print(f"Modelo {args.model} en {dispositivo}", flush=True)
    total = indice.build(chunks)
    print(f"Listo: {total} vectores en {args.out} ({time.perf_counter() - inicio:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
