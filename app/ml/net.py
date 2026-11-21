"""Red neuronal del clasificador de jugadas (PyTorch).

Una CNN residual pequeña sobre el tablero (26 × 8 × 8, ver board_tensor.py): las
convoluciones ven patrones locales (piezas que se atacan, defensas, estructura de
peones) y, apilando bloques, relaciones a más distancia. Es la misma idea que las redes
de los motores modernos (AlphaZero, Leela, el NNUE de Stockfish), en miniatura.

Opcionalmente recibe también las variables escritas a mano (features.py): así se
compara "solo tablero" con "tablero + variables".
"""

import torch
from torch import nn

from app.ml.board_tensor import N_PLANOS


class BloqueResidual(nn.Module):
    """conv → BN → ReLU → conv → BN, + atajo. El atajo deja pasar el gradiente aunque
    la red sea profunda (sin él, apilar capas empeora el entrenamiento)."""

    def __init__(self, canales: int) -> None:
        super().__init__()
        self.c1 = nn.Conv2d(canales, canales, 3, padding=1, bias=False)
        self.b1 = nn.BatchNorm2d(canales)
        self.c2 = nn.Conv2d(canales, canales, 3, padding=1, bias=False)
        self.b2 = nn.BatchNorm2d(canales)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = torch.relu(self.b1(self.c1(x)))
        return torch.relu(x + self.b2(self.c2(y)))


class MoveClassifier(nn.Module):
    def __init__(self, n_escalares: int = 0, canales: int = 64, bloques: int = 6) -> None:
        super().__init__()
        self.n_escalares = n_escalares
        self.entrada = nn.Sequential(
            nn.Conv2d(N_PLANOS, canales, 3, padding=1, bias=False), nn.BatchNorm2d(canales), nn.ReLU()
        )
        self.cuerpo = nn.Sequential(*[BloqueResidual(canales) for _ in range(bloques)])
        self.reduccion = nn.Sequential(nn.Conv2d(canales, 8, 1), nn.ReLU(), nn.Flatten())  # 8 × 64 = 512
        self.cabeza = nn.Sequential(
            nn.Linear(512 + n_escalares, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 1)
        )

    def forward(self, tablero: torch.Tensor, escalares: torch.Tensor | None = None) -> torch.Tensor:
        """tablero: (B, 26, 8, 8) float; escalares: (B, n) ya normalizados. Devuelve logits (B,)."""
        h = self.reduccion(self.cuerpo(self.entrada(tablero)))
        if self.n_escalares:
            h = torch.cat([h, escalares], dim=1)
        return self.cabeza(h).squeeze(1)
