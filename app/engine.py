"""Pool de procesos de Stockfish para la API.

Un SimpleEngine de python-chess es seguro entre hilos, pero cada orden nueva CANCELA
la anterior: dos peticiones que compartieran motor se pisarían el análisis. Aquí cada
petición toma un motor en exclusiva (cola bloqueante) y lo devuelve al terminar. Con
`size` motores, como mucho `size` análisis van a la vez; el resto espera turno.

Los motores se abren la primera vez que hacen falta (arrancar Stockfish carga la red
NNUE, ~0,3 s) y se reutilizan; `close()` los cierra al apagar la API.
"""

import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress

import chess.engine


class EngineUnavailableError(Exception):
    """No hay Stockfish instalado o no arranca."""


class EnginePool:
    def __init__(self, path: str | None, size: int = 2, timeout: float = 60.0) -> None:
        self.path = path
        self.size = size
        self.timeout = timeout  # espera máxima por un motor libre
        self._libres: queue.Queue[chess.engine.SimpleEngine] = queue.Queue()
        self._creados = 0
        self._lock = threading.Lock()
        self._todos: list[chess.engine.SimpleEngine] = []

    def _crear(self) -> chess.engine.SimpleEngine:
        if self.path is None:
            raise EngineUnavailableError("Stockfish no está instalado (ver README)")
        try:
            engine = chess.engine.SimpleEngine.popen_uci(self.path)
        except (OSError, chess.engine.EngineError) as e:
            raise EngineUnavailableError(f"No se pudo arrancar Stockfish: {e}") from e
        engine.configure({"Threads": 1, "Hash": 64})
        self._todos.append(engine)
        return engine

    @contextmanager
    def engine(self) -> Iterator[chess.engine.SimpleEngine]:
        """Presta un motor en exclusiva durante el bloque `with`."""
        with self._lock:
            crear = self._libres.empty() and self._creados < self.size
            if crear:
                self._creados += 1
        if crear:
            try:
                engine = self._crear()
            except Exception:
                with self._lock:
                    self._creados -= 1
                raise
        else:
            try:
                engine = self._libres.get(timeout=self.timeout)
            except queue.Empty:
                raise EngineUnavailableError("Todos los motores están ocupados; reintenta") from None
        try:
            yield engine
        except chess.engine.EngineTerminatedError:
            # El proceso murió: no se devuelve a la cola; la próxima vez se crea otro.
            with self._lock:
                self._creados -= 1
                self._todos.remove(engine)
            raise
        else:
            self._libres.put(engine)

    def close(self) -> None:
        for engine in self._todos:
            with suppress(chess.engine.EngineTerminatedError):  # ya estaba muerto: nada que cerrar
                engine.quit()
        self._todos.clear()
