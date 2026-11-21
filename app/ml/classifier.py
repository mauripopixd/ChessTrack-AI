"""Carga el clasificador entrenado (scripts/train_classifier.py) para usarlo en la API."""

from pathlib import Path

import joblib
import pandas as pd

from app.ml.features import FEATURES


class ErrorClassifier:
    """Envoltorio del Random Forest guardado: probabilidad de que cada jugada sea un error."""

    def __init__(self, modelo, features: list[str], umbral: float) -> None:
        if features != FEATURES:
            # El modelo se entrenó con otras columnas: sus predicciones no tendrían sentido.
            raise ValueError("El modelo no coincide con app/ml/features.py; vuelve a entrenarlo")
        self.modelo = modelo
        self.umbral = umbral

    @classmethod
    def load(cls, ruta: str | Path) -> "ErrorClassifier | None":
        """None si el archivo no existe: el análisis funciona igual, solo con Stockfish."""
        ruta = Path(ruta)
        if not ruta.exists():
            return None
        datos = joblib.load(ruta)
        return cls(datos["modelo"], datos["features"], datos["umbral"])

    def error_probs(self, filas: list[dict[str, float]]) -> list[float]:
        if not filas:
            return []
        X = pd.DataFrame(filas, columns=FEATURES)  # mismas columnas, mismo orden que al entrenar
        return [float(p) for p in self.modelo.predict_proba(X)[:, 1]]
