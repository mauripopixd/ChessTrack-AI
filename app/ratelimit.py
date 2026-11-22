"""Límite de intentos por IP para login y registro (Etapa 6: la app ya es pública).

Ventana deslizante en memoria: por cada clave (p. ej. "login:1.2.3.4") se guardan las
horas de los últimos intentos y se rechaza si ya hay `max` dentro de la ventana.

En memoria vale porque la API corre en UN proceso (docker-compose.prod.yml). Con varias
réplicas haría falta un almacén compartido (Redis o la BD); queda anotado en
docs/decisiones.md §12. El límite del coach (respuestas del LLM) sí está en la BD.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    def __init__(self, max_hits: int, window_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_hits = max_hits
        self.window_s = window_s
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()  # FastAPI ejecuta los endpoints síncronos en varios hilos

    def hit(self, key: str) -> float | None:
        """Cuenta un intento. None si se permite; si no, segundos hasta poder reintentar."""
        ahora = self.clock()
        with self._lock:
            golpes = self._hits[key]
            while golpes and golpes[0] <= ahora - self.window_s:
                golpes.popleft()
            if len(golpes) >= self.max_hits:
                return golpes[0] + self.window_s - ahora
            golpes.append(ahora)
            if len(self._hits) > 50_000:  # que un ataque con muchas IP no llene la memoria
                self._purgar(ahora)
            return None

    def _purgar(self, ahora: float) -> None:
        for clave in [k for k, g in self._hits.items() if not g or g[-1] <= ahora - self.window_s]:
            del self._hits[clave]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    # Con --proxy-headers, uvicorn ya pone aquí la IP de X-Forwarded-For (la del túnel).
    return request.client.host if request.client else "desconocida"


def limit(limiter: SlidingWindowLimiter, nombre: str):
    """Dependencia de FastAPI: 429 con Retry-After al pasarse."""

    def dependencia(request: Request) -> None:
        espera = limiter.hit(f"{nombre}:{client_ip(request)}")
        if espera is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Demasiados intentos: espera un poco y vuelve a probar",
                headers={"Retry-After": str(int(espera) + 1)},
            )

    return dependencia


# 10 logins cada 5 minutos por IP: de sobra para una persona, inútil para adivinar contraseñas.
LOGIN = SlidingWindowLimiter(max_hits=10, window_s=300)
# 5 cuentas nuevas por hora y por IP: frena a quien cree cuentas en masa para gastar el LLM.
REGISTER = SlidingWindowLimiter(max_hits=5, window_s=3600)
