"""Grafo LangGraph del coach: un turno = una jugada del usuario o una pregunta.

    START ─┬─ jugada ──► jugada_usuario ──► jugada_coach ──┬─ error del usuario ─► comentario ─► coach
           │                 │ (ilegal)                     └─ jugada buena ───────────────────► END
           │                 └─────────────────────────────────────────────────────────────────► END
           └─ pregunta ─► pregunta ─► coach ◄──► herramientas
                                          └──────────────────────────────────────────────────► END

- Los nodos de jugada son código normal (deterministas, gratis, sin LLM).
- El LLM (nodo `coach`) solo entra para explicar: cuando se le pregunta, o para comentar
  brevemente un error del usuario. Llama a las herramientas (tools.py) en bucle hasta
  tener lo que necesita; `recursion_limit` corta bucles infinitos.
- Se trazan en LangSmith si están definidas LANGSMITH_TRACING y LANGSMITH_API_KEY.
"""

from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.coach.game import CoachGame, GameOverError, IllegalMoveError, MoveReport
from app.coach.tools import MotorFn, make_tools

SYSTEM = """Eres el coach de ajedrez de ChessTrack AI: juegas contra el usuario y le explicas la partida.

Reglas:
- Antes de afirmar quién va mejor, qué jugada es buena o qué se amenaza, CONSULTA las herramientas.
  No inventes evaluaciones ni jugadas.
- Si el usuario pregunta por una jugada concreta ("¿y si juego d5?"), usa evaluar_jugada con ella.
- Menciona SOLO jugadas, capturas y amenazas que aparezcan en los datos de las herramientas. No
  calcules variantes por tu cuenta ni supongas piezas: dónde está cada una viene en el estado.
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


class CoachState(TypedDict, total=False):
    jugada: str | None  # entrada: jugada del usuario (SAN o UCI)
    pregunta: str | None  # entrada: pregunta libre
    comentar: bool  # entrada: comentar los errores del usuario (False si agotó su límite de LLM)
    messages: Annotated[list[AnyMessage], add_messages]
    informe_usuario: MoveReport | None
    informe_coach: MoveReport | None
    error: str | None
    llm_error: str | None  # el LLM falló (red, 429 en todos los proveedores…): sin respuesta


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
        sistema = SYSTEM + ESTADO.format(estado=por_nombre["estado_partida"].invoke({}))
        mensajes = [SystemMessage(sistema), *previos, *state["messages"]]
        rondas = sum(1 for m in state["messages"] if isinstance(m, AIMessage) and m.tool_calls)
        try:
            if rondas >= MAX_RONDAS:  # corta bucles (p. ej. el modelo repite la misma herramienta)
                return {"messages": [llm_sin_tools.invoke([*mensajes, HumanMessage(CIERRE)])]}
            return {"messages": [llm.invoke(mensajes)]}
        except Exception as e:  # noqa: BLE001 - cualquier fallo del proveedor: la jugada ya está hecha
            # Sin mensaje nuevo, tools_condition manda a END. El turno termina sin respuesta.
            return {"llm_error": f"{type(e).__name__}: {str(e)[:200]}"}

    g = StateGraph(CoachState)
    g.add_node("jugada_usuario", jugada_usuario)
    g.add_node("jugada_coach", jugada_coach)
    g.add_node("comentario", comentario)
    g.add_node("pregunta", pregunta)
    g.add_node("coach", coach)
    g.add_node("herramientas", ToolNode(tools))
    g.add_conditional_edges(START, entrada, ["jugada_usuario", "pregunta"])
    g.add_conditional_edges("jugada_usuario", tras_jugada_usuario, ["jugada_coach", END])
    g.add_conditional_edges("jugada_coach", tras_jugada_coach, ["comentario", END])
    g.add_edge("comentario", "coach")
    g.add_edge("pregunta", "coach")
    g.add_conditional_edges("coach", tools_condition, {"tools": "herramientas", END: END})
    g.add_edge("herramientas", "coach")
    return g.compile()


def respuesta_final(state: dict[str, Any]) -> AIMessage | None:
    """Último mensaje del coach con texto (no una petición de herramienta)."""
    for m in reversed(state.get("messages") or []):
        if isinstance(m, AIMessage) and m.content and not m.tool_calls:
            return m
    return None
