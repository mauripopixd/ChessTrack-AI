"""Índice vectorial de la teoría de aperturas: embeddings + Chroma.

- Embeddings multilingües (sentence-transformers): las preguntas llegan en español y el
  corpus está en inglés; el modelo pone "defensa siciliana" y "Sicilian defence" cerca en
  el mismo espacio.
- Modelo por defecto `BAAI/bge-m3`, elegido midiendo (scripts/eval_retrieval.py, 20
  preguntas): acierto@5 95 % frente a 80 % de multilingual-e5-small y e5-base. Para un RAG
  importa acierto@k (el LLM recibe varios fragmentos), no solo el primero. Coste: 568 M de
  parámetros (2,3 GB) y 17 ms por búsqueda con GPU frente a 10 ms.
- Los modelos E5 se entrenaron con prefijos ("query: " / "passage: "); BGE-M3 no usa.
- Chroma guarda los vectores en disco (data/vectorstore/) y busca por similitud coseno.
"""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from app.rag.corpus import Chunk

MODELO = "BAAI/bge-m3"
# Prefijos con los que se entrenó cada modelo (pregunta, documento). E5 los necesita;
# BGE-M3 no usa ninguno.
PREFIJOS = {
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
    "BAAI/bge-m3": ("", ""),
}


@dataclass(frozen=True, slots=True)
class Hit:
    id: str
    text: str
    source: str
    title: str
    url: str
    moves: str
    name: str | None
    eco: str | None
    license: str
    score: float  # similitud coseno (1 = idéntico)


def coleccion_para(modelo: str) -> str:
    """Un índice por modelo: vectores de modelos distintos no se pueden mezclar."""
    return "openings__" + modelo.replace("/", "__").replace(".", "_")


class OpeningIndex:
    def __init__(self, persist_dir: Path, modelo: str = MODELO, device: str | None = None) -> None:
        if modelo not in PREFIJOS:
            raise ValueError(f"Modelo sin prefijos conocidos: {modelo} (añádelo a PREFIJOS)")
        self.nombre_modelo = modelo
        self.prefijo_pregunta, self.prefijo_documento = PREFIJOS[modelo]
        self.coleccion = coleccion_para(modelo)
        self.modelo = SentenceTransformer(modelo, device=device)
        self.cliente = chromadb.PersistentClient(path=str(persist_dir))

    def _vectores(self, textos: list[str], prefijo: str) -> list[list[float]]:
        # normalize_embeddings: con vectores de norma 1, coseno = producto escalar.
        return self.modelo.encode(
            [prefijo + t for t in textos], batch_size=64, normalize_embeddings=True
        ).tolist()

    def build(self, chunks: list[Chunk], lote: int = 1000) -> int:
        """Reconstruye el índice desde cero (borra el anterior)."""
        if self.coleccion in [c.name for c in self.cliente.list_collections()]:
            self.cliente.delete_collection(self.coleccion)
        coleccion = self.cliente.create_collection(
            self.coleccion, configuration={"hnsw": {"space": "cosine"}}
        )
        for i in range(0, len(chunks), lote):
            parte = chunks[i : i + lote]
            coleccion.add(
                ids=[c.id for c in parte],
                documents=[c.text for c in parte],
                embeddings=self._vectores([c.text for c in parte], self.prefijo_documento),
                metadatas=[
                    {
                        "source": c.source,
                        "title": c.title,
                        "url": c.url,
                        "moves": c.moves,
                        "name": c.name or "",
                        "eco": c.eco or "",
                        "license": c.license,
                    }  # fmt: skip
                    for c in parte
                ],
            )
        return coleccion.count()

    def search(self, pregunta: str, k: int = 5, source: str | None = None) -> list[Hit]:
        coleccion = self.cliente.get_collection(self.coleccion)
        r = coleccion.query(
            query_embeddings=self._vectores([pregunta], self.prefijo_pregunta),
            n_results=k,
            where={"source": source} if source else None,
        )
        return [
            Hit(
                id=i,
                text=doc,
                source=m["source"],
                title=m["title"],
                url=m["url"],
                moves=m["moves"],
                name=m["name"] or None,
                eco=m["eco"] or None,
                license=m["license"],
                score=round(1 - dist, 4),  # Chroma devuelve distancia coseno = 1 - similitud
            )  # fmt: skip
            for i, doc, m, dist in zip(
                r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0], strict=True
            )
        ]
