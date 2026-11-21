"""Carga del clasificador guardado (sin el modelo real de 110 MB: uno diminuto)."""

import chess
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from app.ml.classifier import ErrorClassifier
from app.ml.features import FEATURES, game_features


def _guardar(ruta, features=FEATURES, umbral=0.4):
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.random((200, len(features))), columns=features)
    y = (X.iloc[:, 0] > 0.5).astype(int)
    modelo = RandomForestClassifier(n_estimators=5, random_state=0).fit(X, y)
    joblib.dump({"modelo": modelo, "features": features, "umbral": umbral}, ruta)


def test_carga_y_predice(tmp_path):
    _guardar(tmp_path / "rf.joblib")
    clf = ErrorClassifier.load(tmp_path / "rf.joblib")
    assert clf.umbral == 0.4
    probs = clf.error_probs(game_features(["e2e4", "e7e5", "g1f3"]))
    assert len(probs) == 3 and all(0 <= p <= 1 for p in probs)


def test_sin_archivo_devuelve_none(tmp_path):
    assert ErrorClassifier.load(tmp_path / "no_existe.joblib") is None


def test_modelo_con_otras_columnas_se_rechaza(tmp_path):
    _guardar(tmp_path / "viejo.joblib", features=FEATURES[:-1])
    with pytest.raises(ValueError, match="vuelve a entrenarlo"):
        ErrorClassifier.load(tmp_path / "viejo.joblib")


def test_sin_jugadas(tmp_path):
    _guardar(tmp_path / "rf.joblib")
    assert ErrorClassifier.load(tmp_path / "rf.joblib").error_probs([]) == []


def test_posicion_no_estandar(tmp_path):
    _guardar(tmp_path / "rf.joblib")
    filas = game_features(["a7a8q"], initial_fen="8/P7/8/8/8/8/8/k6K w - - 0 1")
    assert len(ErrorClassifier.load(tmp_path / "rf.joblib").error_probs(filas)) == 1
    assert chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1").is_valid()
