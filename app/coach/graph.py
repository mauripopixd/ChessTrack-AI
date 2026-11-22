"""Grafo LangGraph del coach: un turno = una jugada del usuario o una pregunta.

    START ─┬─ jugada ──► jugada_usuario ──► jugada_coach ──┬─ error del usuario ─► comentario ─► coach
           │                 │ (ilegal)                     └─ jugada buena ───────────────────► END
           │                 └─────────────────────────────────────────────────────────────────► END
           └─ pregunta ─► pregunta ─► coach ◄──► herramientas
                                          └─► verificar ─(jugada inventada)─► reescribir ───► END

- Los nodos de jugada son código normal (deterministas, gratis, sin LLM).
- El LLM (nodo `coach`) solo entra para explicar: cuando se le pregunta, o para comentar
  brevemente un error del usuario. Llama a las herramientas (tools.py) en bucle hasta
  tener lo que necesita; `recursion_limit` corta bucles infinitos.
- `verificar` comprueba con código las jugadas de pieza que menciona la respuesta (Nf3,
  Bxc6…): si no se pueden jugar ahora ni salen en los datos, el LLM reescribe sin ellas.
- Se trazan en LangSmith si están definidas LANGSMITH_TRACING y LANGSMITH_API_KEY.
"""

import re
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

import chess
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.coach.game import CoachGame, GameOverError, IllegalMoveError, MoveReport
from app.coach.lenguaje import PROMPT_NIVEL
from app.coach.tools import MotorFn, make_tools

SYSTEM = """Eres el coach de ajedrez de ChessTrack AI: juegas contra el usuario y le explicas la partida.

Reglas:
- Antes de afirmar quién va mejor, qué jugada es buena o qué se amenaza, CONSULTA las herramientas.
  No inventes evaluaciones ni jugadas.
- Si el usuario pregunta por una jugada concreta ("¿y si juego d5?"), usa evaluar_jugada con ella.
- Menciona SOLO jugadas, capturas y amenazas que aparezcan en los datos de las herramientas. No
  calcules variantes por tu cuenta ni supongas piezas: dónde está cada una viene en el estado.
- Una captura seguida de recaptura es un CAMBIO y no gana material: usa el "Balance" de las
  herramientas para decir si se gana, se pierde o se cambia, y quién queda con peones doblados.
- No afirmes qué ataca una jugada ni qué diagonal, columna o casilla abre si no viene en los datos
  ("ataca …", "Casillas que cambian …").
- Explica con ideas humanas (planes, amenazas, piezas colgando, seguridad del rey), no solo números.
- Si usas teoría de aperturas (buscar_teoria), cita la fuente con [n] y su enlace.
- Responde en español (blancas/negras, nunca White/Black), cercano y claro, en 120 palabras como
  máximo. Jugadas en SAN (Nf3, O-O).
- Si el usuario pregunta qué jugar, dale una pista o idea antes que la jugada exacta, salvo que la pida."""

COMENTARIO = (
    "Acabo de jugar {san} y fue un {etiqueta}. Explícame en 2 o 3 frases qué falló y qué idea era "
    "mejor, usando SOLO estos datos del análisis (no menciones piezas, casillas ni jugadas que no "
    "aparezcan aquí):\n\n{analisis}{respuesta}"
)
# La línea del motor es la MEJOR respuesta, no la que jugó el coach (con nivel bajo puede
# jugar otra): sin esto, el modelo contaba "Nxa6" cuando en el tablero había pasado bxa6.
RESPUESTA = "\nEl coach respondió de verdad: {coach}. Si es distinta de la mejor respuesta, di cuál jugó."
ESTADO = (
    "\n\nEstado actual de la partida (datos exactos, no los contradigas; si un mensaje anterior "
    "dice otra cosa, está desfasado):\n{estado}"
)
HISTORIAL = 6  # mensajes previos de chat que ve el LLM (más = más tokens del límite gratuito)
MAX_RONDAS = 3  # rondas LLM → herramientas; después se le obliga a responder sin herramientas
CIERRE = "Ya tienes datos suficientes: responde ahora al usuario sin pedir más herramientas."
# Jugadas de pieza en SAN ("Nf3", "Bxc6", "Nb1" de "Nb1-c3"). Los peones no: "c3" o "e4" se
# confunden con nombres de casillas, y ahí los falsos avisos serían más que los aciertos.
SAN_PIEZA = re.compile(r"\b([KQRBN][a-h]?[1-8]?x?[a-h][1-8])")
REESCRIBIR = (
    "Revisión automática de tu respuesta, comparada con los datos de las herramientas:\n{problemas}\n"
    "Reescribe la respuesta completa corrigiendo eso y usando solo los datos. No menciones esta revisión."
)
JUGADA_INVENTADA = (
    "- Mencionas {jugadas}: no se pueden jugar en la posición actual ni aparecen en los datos "
    "(por ejemplo, una pieza que ya está en esa casilla o que no existe)."
)
# "te quedan", "dejándote", "te deja", "quedas con", "tendrás", "tus": peones doblados del usuario.
_DOBLADOS_TUYOS = re.compile(
    r"(\bte\b|\w+ndote\b|\w+rte\b|quedas con|quedarías con|tendrías|tendrás|\btus\b)"
    r"[^.]{0,30}peones doblados"
)
_DOBLADOS_RIVAL = re.compile(
    r"peones doblados (del rival|suyos)|(rival|él|ella)[^.]{0,20}(queda|quedan|quedará|termina|tendrá)"
    r"[^.]{0,15}peones doblados"
)
_GANA_PIEZA = re.compile(
    r"\b(ganas|ganarías|ganarás|te llevas)\s+(el|un|una|la)\s+(caballo|alfil|torre|dama)"
)


def hechos_contradichos(texto: str, datos: str) -> list[str]:
    """Afirmaciones del texto que contradicen los datos calculados (balance de cada línea).
    Son los errores que más se repetían: confundir de quién son los peones doblados y llamar
    "ganar una pieza" a un cambio."""
    t = texto.lower()
    problemas = []
    tuyos, rival = "peones doblados tuyos" in datos, "peones doblados del rival" in datos
    # Si la misma respuesta también los atribuye al rival ("tu rival queda con…"), no se marca.
    if _DOBLADOS_TUYOS.search(t) and not _DOBLADOS_RIVAL.search(t) and rival and not tuyos:
        problemas.append(
            "- Según los datos, los peones doblados quedan en el bando del RIVAL, no en el del usuario."
        )
    if _DOBLADOS_RIVAL.search(t) and tuyos and not rival:
        problemas.append("- Según los datos, los peones doblados serían del USUARIO, no del rival.")
    if _GANA_PIEZA.search(t) and "GANAS material" not in datos:
        problemas.append(
            "- Dices que se gana una pieza, pero ninguna línea de los datos gana material: una captura "
            "seguida de recaptura es un cambio."
        )
    return problemas


def jugadas_inventadas(texto: str, board, datos: str) -> list[str]:
    """Jugadas de pieza del texto que no son legales ahora ni aparecen en `datos` (las salidas
    de las herramientas y el estado: ahí están las líneas del motor y las jugadas ya hechas)."""
    mencionadas = set(SAN_PIEZA.findall(texto))
    if not mencionadas:
        return []
    posibles = jugadas_plausibles(board)
    return sorted(j for j in mencionadas if j not in posibles and j not in datos)


def jugadas_plausibles(board) -> set[str]:
    """Jugadas que el coach puede nombrar con sentido: las legales ahora, las respuestas del
    rival a cada una, y las del mismo bando en la jugada siguiente con OTRA pieza ("c3 y
    luego Bc2"). Mover dos veces la misma pieza queda fuera: así "Ne2" con el caballo ya en
    e2 (vía Ng3-e2) se sigue detectando como inventada."""
    san = lambda b, m: b.san(m).rstrip("+#")  # noqa: E731
    posibles = set()
    for m in board.legal_moves:
        posibles.add(san(board, m))
        tras = board.copy(stack=False)
        tras.push(m)
        posibles.update(san(tras, r) for r in tras.legal_moves)  # respuestas del rival
        if tras.is_check():
            continue  # con el rey en jaque no se puede "pasar" el turno del rival
        tras.push(chess.Move.null())
        posibles.update(san(tras, s) for s in tras.legal_moves if s.from_square != m.to_square)
    return posibles


class CoachState(TypedDict, total=False):
    jugada: str | None  # entrada: jugada del usuario (SAN o UCI)
    pregunta: str | None  # entrada: pregunta libre
    comentar: bool  # entrada: comentar los errores del usuario (False si agotó su límite de LLM)
    messages: Annotated[list[AnyMessage], add_messages]
    informe_usuario: MoveReport | None
    informe_coach: MoveReport | None
    error: str | None
    llm_error: str | None  # el LLM falló (red, 429 en todos los proveedores…): sin respuesta
    inventadas: list[str] | None  # jugadas que el verificador hizo quitar (queda en la traza)
    contradicciones: list[str] | None  # afirmaciones contra los datos que hizo corregir


def build_graph(
    game: CoachGame,
    motor: MotorFn,
    llm_factory: Callable[[list[BaseTool]], BaseChatModel],
    classifier=None,
    retriever=None,
):
    """Compila el grafo para ESTA partida (las herramientas leen `game` por closure)."""
    tools = make_tools(game, motor, classifier, retriever)
    por_nombre = {t.name: t for t in tools}
    llm = llm_factory(tools)
    llm_sin_tools = llm_factory([])

    def sistema_actual() -> str:
        # Reglas + cómo hablarle según lo que sabe de ajedrez + estado exacto de la partida
        nivel = PROMPT_NIVEL.get(game.conocimiento, "")
        return SYSTEM + nivel + ESTADO.format(estado=por_nombre["estado_partida"].invoke({}))

    def entrada(state: CoachState) -> str:
        return "jugada_usuario" if state.get("jugada") else "pregunta"

    def jugada_usuario(state: CoachState) -> dict:
        try:
            with motor() as eng:
                return {"informe_usuario": game.play_user_move(state["jugada"], eng), "error": None}
        except (IllegalMoveError, GameOverError) as e:
            return {"error": str(e)}

    def tras_jugada_usuario(state: CoachState) -> str:
        return END if state.get("error") else "jugada_coach"

    def jugada_coach(state: CoachState) -> dict:
        with motor() as eng:
            return {"informe_coach": game.play_coach_move(eng)}

    def tras_jugada_coach(state: CoachState) -> str:
        informe = state.get("informe_usuario")
        if not state.get("comentar", True):
            return END
        return "comentario" if informe and informe.label in ("error", "error_grave") else END

    def comentario(state: CoachState) -> dict:
        r = state["informe_usuario"]
        etiqueta = "error grave" if r.label == "error_grave" else "error"
        # El análisis va ya en el mensaje: el modelo no tiene que pedirlo (una llamada menos al LLM)
        # y, sobre todo, explica a partir de datos exactos. Sin esto se inventaba casillas.
        analisis = por_nombre["analizar_mi_ultima_jugada"].invoke({})
        coach = state.get("informe_coach")
        respuesta = RESPUESTA.format(coach=coach.san) if coach else ""
        texto = COMENTARIO.format(san=r.san, etiqueta=etiqueta, analisis=analisis, respuesta=respuesta)
        return {"messages": [HumanMessage(texto)]}

    def pregunta(state: CoachState) -> dict:
        return {"messages": [HumanMessage(state["pregunta"])]}

    def coach(state: CoachState) -> dict:
        previos = [HumanMessage(t) if rol == "user" else AIMessage(t) for rol, t in game.chat[-HISTORIAL:]]
        sistema = sistema_actual()
        mensajes = [SystemMessage(sistema), *previos, *state["messages"]]
        rondas = sum(1 for m in state["messages"] if isinstance(m, AIMessage) and m.tool_calls)
        try:
            if rondas >= MAX_RONDAS:  # corta bucles (p. ej. el modelo repite la misma herramienta)
                return {"messages": [llm_sin_tools.invoke([*mensajes, HumanMessage(CIERRE)])]}
            if rondas == 0 and state.get("pregunta"):
                # Primera llamada de una pregunta: tiene que usar al menos una herramienta. Pedirlo en
                # el prompt no bastaba: a "¿qué plan me recomiendas?" respondía de memoria e inventaba.
                return {"messages": [llm.invoke(mensajes, tool_choice="required")]}
            return {"messages": [llm.invoke(mensajes)]}
        except Exception as e:  # noqa: BLE001 - cualquier fallo del proveedor: la jugada ya está hecha
            # Sin mensaje nuevo, tools_condition manda a END. El turno termina sin respuesta.
            return {"llm_error": f"{type(e).__name__}: {str(e)[:200]}"}

    def verificar(state: CoachState) -> dict:
        final = state["messages"][-1] if state.get("messages") else None
        if not isinstance(final, AIMessage) or not final.content:
            return {}  # el LLM falló: no hay nada que revisar
        datos = "\n".join(str(m.content) for m in state["messages"][:-1])
        datos += "\n" + por_nombre["estado_partida"].invoke({})
        inventadas = jugadas_inventadas(final.content, game.board, datos)
        contradicciones = hechos_contradichos(final.content, datos)
        problemas = (
            [JUGADA_INVENTADA.format(jugadas=", ".join(inventadas))] if inventadas else []
        ) + contradicciones
        if not problemas:
            return {}
        sistema = sistema_actual()
        aviso = HumanMessage(REESCRIBIR.format(problemas="\n".join(problemas)))
        resultado = {"inventadas": inventadas or None, "contradicciones": contradicciones or None}
        try:
            corregida = llm_sin_tools.invoke([SystemMessage(sistema), *state["messages"], aviso])
        except Exception:  # noqa: BLE001 - sin LLM para corregir, se queda la respuesta original
            return resultado
        return {"messages": [corregida], **resultado}

    g = StateGraph(CoachState)
    g.add_node("jugada_usuario", jugada_usuario)
    g.add_node("jugada_coach", jugada_coach)
    g.add_node("comentario", comentario)
    g.add_node("pregunta", pregunta)
    g.add_node("coach", coach)
    g.add_node("herramientas", ToolNode(tools))
    g.add_node("verificar", verificar)
    g.add_conditional_edges(START, entrada, ["jugada_usuario", "pregunta"])
    g.add_conditional_edges("jugada_usuario", tras_jugada_usuario, ["jugada_coach", END])
    g.add_conditional_edges("jugada_coach", tras_jugada_coach, ["comentario", END])
    g.add_edge("comentario", "coach")
    g.add_edge("pregunta", "coach")
    g.add_conditional_edges("coach", tools_condition, {"tools": "herramientas", END: "verificar"})
    g.add_edge("herramientas", "coach")
    g.add_edge("verificar", END)
    return g.compile()


def respuesta_final(state: dict[str, Any]) -> AIMessage | None:
    """Último mensaje del coach con texto (no una petición de herramienta)."""
    for m in reversed(state.get("messages") or []):
        if isinstance(m, AIMessage) and m.content and not m.tool_calls:
            return m
    return None
