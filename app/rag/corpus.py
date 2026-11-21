"""Del corpus descargado (scripts/download_openings.py) a fragmentos listos para indexar.

Cada fragmento lleva una cabecera con apertura, ECO y jugadas. Sin ella, un párrafo como
"Black accepts the pawn..." no dice de qué apertura habla, y ni la búsqueda ni el LLM
podrían saberlo.
"""

import csv
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PREFIJO = "Chess Opening Theory/"
MIN_CARACTERES = 200  # páginas más cortas son esbozos sin teoría: solo meten ruido
MAX_CARACTERES = 1200  # fragmentos cortos = búsqueda más precisa y contexto más barato
LICENCIAS = {"wikibooks": "CC BY-SA 4.0", "lichess": "CC0"}
LICHESS_URL = "https://github.com/lichess-org/chess-openings/blob/master/{}.tsv"

# Jugadas en los títulos de Wikibooks. Negras se comprueba ANTES que blancas:
# "1...c5" también encaja con el patrón de blancas ("1." seguido de "..c5").
_NEGRAS = re.compile(r"\d+\.\.\.\s*(\S+)")
_BLANCAS = re.compile(r"(\d+)\.\s*(\S+)")
# A partir de estos títulos solo hay tablas de jugadas, bibliografía o enlaces: sin teoría.
_SECCIONES_FINALES = re.compile(
    r"^[ \t=]*(Theory tables?|References|Statistics|External links|See also|Further reading|Sources)[ \t=]*$",
    re.MULTILINE | re.IGNORECASE,
)
_LINEAS_VACIAS = re.compile(r"\n{3,}")
_PARRAFOS = re.compile(r"\n\s*\n")
_FRASES = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    text: str  # lo que se indexa y se le da al LLM (cabecera + contenido)
    source: str  # "wikibooks" o "lichess"
    title: str
    url: str
    moves: str  # "1. e4 c5 2. Nf3"
    name: str | None  # "Sicilian Defense" (de Lichess, si coincide)
    eco: str | None  # "B27"

    @property
    def license(self) -> str:
        return LICENCIAS[self.source]


def moves_from_title(title: str) -> str:
    """'Chess Opening Theory/1. e4/1...c5/2. Nf3' → '1. e4 c5 2. Nf3' (formato de Lichess)."""
    jugadas = []
    for parte in title.removeprefix(PREFIJO).split("/"):
        parte = parte.strip()
        if m := _NEGRAS.fullmatch(parte):
            jugadas.append(m[1])
        elif m := _BLANCAS.fullmatch(parte):
            jugadas.append(f"{m[1]}. {m[2]}")
    return " ".join(jugadas)


def load_lichess(carpeta: Path) -> dict[str, tuple[str, str, str]]:
    """{jugadas: (eco, nombre, archivo)} del catálogo de Lichess."""
    catalogo = {}
    for ruta in sorted(carpeta.glob("*.tsv")):
        with open(ruta, encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f, delimiter="\t"):
                catalogo[fila["pgn"]] = (fila["eco"], fila["name"], ruta.stem)
    return catalogo


def _nombre_mas_cercano(moves: str, catalogo: dict) -> tuple[str | None, str | None]:
    """La apertura de Lichess con la secuencia más larga que sea prefijo de `moves`
    (p. ej. 1. e4 c5 2. Nf3 d6 3. g3 → 'Sicilian Defense: Modern Variations')."""
    fichas = moves.split()
    for n in range(len(fichas), 0, -1):
        if (clave := " ".join(fichas[:n])) in catalogo:
            eco, nombre, _ = catalogo[clave]
            return eco, nombre
    return None, None


def limpiar(texto: str) -> str:
    """Corta las secciones finales sin teoría y compacta las líneas vacías."""
    if m := _SECCIONES_FINALES.search(texto):
        texto = texto[: m.start()]
    return _LINEAS_VACIAS.sub("\n\n", texto).strip()


def _cortar_duro(texto: str, maximo: int) -> list[str]:
    """Último recurso para bloques sin párrafos ni puntos (tablas): corta por líneas."""
    trozos, actual = [], ""
    for linea in texto.splitlines() or [texto]:
        linea = linea[:maximo]
        if actual and len(actual) + len(linea) + 1 > maximo:
            trozos.append(actual)
            actual = ""
        actual = f"{actual}\n{linea}".strip()
    return [*trozos, actual] if actual else trozos


def trocear(texto: str, maximo: int = MAX_CARACTERES) -> list[str]:
    """Agrupa párrafos hasta `maximo` caracteres sin partirlos; si uno solo lo supera,
    se parte por frases y, si una frase también lo supera, por líneas."""
    piezas = []
    for p in (p.strip() for p in _PARRAFOS.split(texto)):
        if not p:
            continue
        if len(p) <= maximo:
            piezas.append(p)
        else:
            piezas += [t for frase in _FRASES.split(p) for t in _cortar_duro(frase, maximo)]
    trozos, actual = [], ""
    for pieza in piezas:
        if actual and len(actual) + len(pieza) + 2 > maximo:
            trozos.append(actual)
            actual = ""
        actual = f"{actual}\n\n{pieza}".strip()
    return [*trozos, actual] if actual else trozos


def _cabecera(nombre: str | None, eco: str | None, moves: str) -> str:
    apertura = f"{nombre} ({eco})" if nombre else "Apertura"
    return f"{apertura} · {moves}" if moves else apertura


def wikibooks_chunks(ruta_jsonl: Path, catalogo: dict) -> Iterator[Chunk]:
    for linea in ruta_jsonl.read_text(encoding="utf-8").splitlines():
        pagina = json.loads(linea)
        texto = limpiar(pagina["text"])
        if len(texto) < MIN_CARACTERES:
            continue
        moves = moves_from_title(pagina["title"])
        eco, nombre = _nombre_mas_cercano(moves, catalogo)
        cabecera = _cabecera(nombre, eco, moves)
        for i, trozo in enumerate(trocear(texto)):
            yield Chunk(
                id=f"wb:{pagina['title']}#{i}",
                text=f"{cabecera}\n\n{trozo}",
                source="wikibooks",
                title=pagina["title"].removeprefix(PREFIJO) or "Chess Opening Theory",
                url=pagina["url"],
                moves=moves,
                name=nombre,
                eco=eco,
            )


def lichess_chunks(catalogo: dict) -> Iterator[Chunk]:
    """Una ficha por apertura: sirve para "¿qué jugadas definen la Najdorf?" o "¿qué es B90?"."""
    for moves, (eco, nombre, archivo) in catalogo.items():
        yield Chunk(
            id=f"li:{eco}:{moves}",
            text=f"{nombre} ({eco}): {moves}",
            source="lichess",
            title=nombre,
            url=LICHESS_URL.format(archivo),
            moves=moves,
            name=nombre,
            eco=eco,
        )


def build_chunks(carpeta: Path) -> list[Chunk]:
    catalogo = load_lichess(carpeta / "lichess")
    return [*wikibooks_chunks(carpeta / "wikibooks.jsonl", catalogo), *lichess_chunks(catalogo)]
