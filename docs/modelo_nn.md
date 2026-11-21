# Clasificador de jugadas · red neuronal (PyTorch)

> Generado por `python -m scripts.train_nn`. No editar a mano.

Misma pregunta que el [Random Forest](modelo_rf.md): ¿es esta jugada un error (*error* o *error
grave* según Stockfish), **sin motor**? Misma división temporal y mismas jugadas de prueba, así que
los números se comparan directamente.

## Entrada y arquitectura

- **Tablero** como tensor 26 × 8 × 8 (`app/ml/board_tensor.py`): piezas propias y del rival antes y
  después de la jugada, más las casillas de origen y destino. Siempre visto desde quien mueve.
- **CNN residual** (`app/ml/net.py`): 6 bloques de 64 canales, una reducción 1×1 y un MLP.
  La variante híbrida añade las 28 variables escritas a mano, normalizadas con la media y la
  desviación del entrenamiento.
- Pérdida BCE con `pos_weight` (hay 1 error por cada ~9 jugadas buenas), AdamW, bf16 en NVIDIA GeForce RTX 4070 Laptop GPU.
- **Early stopping** con la PR-AUC de validación: 292,805 jugadas de entrenamiento y
  71,563 de validación, ambas dentro del entrenamiento del RF. La prueba son las mismas
  92,553 jugadas que en `modelo_rf.md`.

## Resultados en prueba (clase positiva = error)

| Modelo | Precisión | Recall | F1 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|
| regla manual | 0.158 | 0.157 | 0.158 | — | — |
| random forest (umbral 0.52) | 0.235 | 0.534 | 0.326 | 0.266 | 0.771 |
| red · solo tablero (umbral 0.42) | 0.183 | 0.555 | 0.276 | 0.195 | 0.718 |
| red · tablero + variables (umbral 0.66) | 0.253 | 0.479 | 0.331 | 0.267 | 0.778 |

Al azar, la PR-AUC sería unos 0.10.

## Entrenamiento

**red · solo tablero** (525,321 parámetros)

| Época | Pérdida | PR-AUC validación |
|---|---|---|
| 1 | 1.1257 | 0.1910 |
| 2 | 1.0733 | 0.1953 |
| 3 | 1.0452 | 0.1995 |
| 4 | 1.0208 | 0.1946 |
| 5 | 0.9949 | 0.1931 |
| 6 | 0.8920 | 0.1881 |

**red · tablero + variables** (528,905 parámetros)

| Época | Pérdida | PR-AUC validación |
|---|---|---|
| 1 | 1.0721 | 0.2441 |
| 2 | 0.9956 | 0.2713 |
| 3 | 0.9553 | 0.2809 |
| 4 | 0.9260 | 0.2730 |
| 5 | 0.9037 | 0.2709 |
| 6 | 0.8208 | 0.2714 |

Tiempo total: 1.2 min
(incluye codificar los tableros si no estaban en caché).
