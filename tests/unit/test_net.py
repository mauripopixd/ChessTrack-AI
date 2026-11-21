"""La red: formas de entrada/salida y que puede aprender (en CPU, sin GPU)."""

import pytest

torch = pytest.importorskip("torch")

from app.ml.board_tensor import N_PLANOS  # noqa: E402
from app.ml.net import MoveClassifier  # noqa: E402


def test_salida_un_logit_por_jugada():
    red = MoveClassifier(bloques=2).eval()
    assert red(torch.zeros(5, N_PLANOS, 8, 8)).shape == (5,)


def test_con_variables_escalares():
    red = MoveClassifier(n_escalares=28, bloques=2).eval()
    assert red(torch.zeros(3, N_PLANOS, 8, 8), torch.zeros(3, 28)).shape == (3,)


def test_aprende_un_patron_trivial():
    # Positivo si hay algo en el plano 25 en la esquina: la red debe poder separarlo.
    torch.manual_seed(0)
    x = torch.zeros(64, N_PLANOS, 8, 8)
    y = torch.zeros(64)
    x[:32, 25, 0, 0] = 1
    y[:32] = 1
    red = MoveClassifier(bloques=1, canales=8)
    opt = torch.optim.Adam(red.parameters(), lr=1e-2)
    # 200 pasos y no menos: BatchNorm evalúa con medias acumuladas que tardan en estabilizarse.
    # Con 60 pasos la red ya acierta en modo train, pero en modo eval aún da 50 %.
    for _ in range(200):
        opt.zero_grad()
        perdida = torch.nn.functional.binary_cross_entropy_with_logits(red(x), y)
        perdida.backward()
        opt.step()
    red.eval()
    with torch.no_grad():
        acierto = ((red(x) > 0).float() == y).float().mean()
    assert acierto == 1.0
