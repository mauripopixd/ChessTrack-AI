"""Límite de intentos por IP (login y registro)."""

from app.ratelimit import SlidingWindowLimiter


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_permite_hasta_el_maximo_y_luego_dice_cuanto_esperar():
    reloj = Reloj()
    lim = SlidingWindowLimiter(max_hits=3, window_s=60, clock=reloj)
    assert [lim.hit("ip") for _ in range(3)] == [None, None, None]
    reloj.t += 10
    assert lim.hit("ip") == 50  # el primero caduca a los 60 s


def test_ventana_deslizante():
    reloj = Reloj()
    lim = SlidingWindowLimiter(max_hits=2, window_s=60, clock=reloj)
    lim.hit("ip")
    reloj.t += 30
    lim.hit("ip")
    reloj.t += 31  # el primero ya salió de la ventana; el segundo sigue
    assert lim.hit("ip") is None
    assert lim.hit("ip") is not None


def test_claves_independientes_y_reset():
    lim = SlidingWindowLimiter(max_hits=1, window_s=60, clock=Reloj())
    assert lim.hit("a") is None and lim.hit("b") is None
    assert lim.hit("a") is not None
    lim.reset()
    assert lim.hit("a") is None
