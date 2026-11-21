"""Descarga el corpus de teoría de aperturas para el RAG (Etapa 5A).

Fuentes (licencias abiertas, verificadas al escribir esto):
- Lichess `chess-openings` (CC0): nombre, código ECO y jugadas de ~3.900 aperturas.
  https://github.com/lichess-org/chess-openings
- Wikibooks "Chess Opening Theory" (CC BY-SA 4.0): ~2.700 páginas con ideas y planes,
  una por secuencia de jugadas. CC BY-SA obliga a citar: el RAG enlaza cada página que usa.
  https://en.wikibooks.org/wiki/Chess_Opening_Theory

    python -m scripts.download_openings            # todo a data/openings/ (no versionado)
    python -m scripts.download_openings --limit 50 # prueba rápida

Usa la API oficial de MediaWiki (no rasca HTML): pide el wikitexto de 50 páginas por
petición (la API de extractos solo da UNA página completa por petición y el servidor
frena con 429) y lo pasa a texto plano con mwparserfromhell. Respeta las normas de uso
de Wikimedia: `maxlag`, pausa entre peticiones y espera lo que diga `Retry-After`.
Es reanudable: no vuelve a pedir lo que ya está en wikibooks.jsonl.
"""

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import mwparserfromhell

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "data" / "openings"
LICHESS = "https://raw.githubusercontent.com/lichess-org/chess-openings/master/{}.tsv"
API = "https://en.wikibooks.org/w/api.php"
PREFIJO = "Chess Opening Theory/"
HEADERS = {"User-Agent": "ChessTrackAI-corpus/0.1 (proyecto educativo)"}
PAUSA_SEG = 2.0
LOTE = 50  # máximo de páginas por petición con prop=revisions


def _get(url: str, params: dict | None = None, intentos: int = 6) -> bytes:
    # Parámetros por POST: 50 títulos largos no caben en una URL (414 URI Too Long).
    cuerpo = urllib.parse.urlencode(params).encode() if params else None
    for intento in range(intentos):
        try:
            peticion = urllib.request.Request(url, data=cuerpo, headers=HEADERS)
            with urllib.request.urlopen(peticion, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or intento == intentos - 1:
                raise
            espera = int(e.headers.get("Retry-After") or 0) or 10 * 2**intento
            print(f"  {e.code}: espero {espera} s (lo pide el servidor)", flush=True)
            time.sleep(espera)
    raise RuntimeError("inalcanzable")


def texto_plano(wikitexto: str) -> str:
    """Wikitexto → texto: quita plantillas y marcas; deja títulos y párrafos."""
    codigo = mwparserfromhell.parse(wikitexto)
    for plantilla in codigo.filter_templates(recursive=False):
        codigo.remove(plantilla)
    texto = codigo.strip_code(normalize=True, collapse=True)
    return "\n".join(linea.rstrip() for linea in texto.splitlines()).strip()


def descargar_lichess() -> int:
    destino = SALIDA / "lichess"
    destino.mkdir(parents=True, exist_ok=True)
    filas = 0
    for letra in "abcde":
        contenido = _get(LICHESS.format(letra))
        (destino / f"{letra}.tsv").write_bytes(contenido)
        filas += contenido.count(b"\n") - 1
    return filas


def titulos_wikibooks() -> list[str]:
    titulos, continuar = [], {}
    while True:
        params = {
            "action": "query", "list": "allpages", "apnamespace": 0, "apprefix": PREFIJO,
            "apfilterredir": "nonredirects", "aplimit": 500, "format": "json", "maxlag": 5,
        }  # fmt: skip
        datos = json.loads(_get(API, params | continuar))
        titulos += [p["title"] for p in datos["query"]["allpages"]]
        if "continue" not in datos:
            return titulos
        continuar = {"apcontinue": datos["continue"]["apcontinue"]}
        time.sleep(PAUSA_SEG)


def descargar_wikibooks(limit: int | None) -> int:
    ruta = SALIDA / "wikibooks.jsonl"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    hechos = set()
    if ruta.exists():
        hechos = {json.loads(linea)["title"] for linea in ruta.read_text(encoding="utf-8").splitlines()}
    pendientes = [t for t in titulos_wikibooks() if t not in hechos][:limit]
    with open(ruta, "a", encoding="utf-8") as f:
        for i in range(0, len(pendientes), LOTE):
            params = {
                "action": "query", "prop": "revisions|info", "rvprop": "content", "rvslots": "main",
                "inprop": "url", "titles": "|".join(pendientes[i : i + LOTE]), "format": "json",
                "formatversion": 2, "maxlag": 5,
            }  # fmt: skip
            for pagina in json.loads(_get(API, params))["query"]["pages"]:
                revisiones = pagina.get("revisions") or []
                texto = texto_plano(revisiones[0]["slots"]["main"]["content"]) if revisiones else ""
                if texto:
                    registro = {"title": pagina["title"], "url": pagina["fullurl"], "text": texto}
                    f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            print(f"  wikibooks: {min(i + LOTE, len(pendientes))}/{len(pendientes)}", flush=True)
            time.sleep(PAUSA_SEG)
    return len(pendientes)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, help="solo las primeras N páginas de Wikibooks")
    args = parser.parse_args()
    print(f"Lichess: {descargar_lichess()} aperturas", flush=True)
    print(f"Wikibooks: {descargar_wikibooks(args.limit)} páginas nuevas", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
