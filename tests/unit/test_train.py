"""Piezas del entrenamiento que, si fallan, invalidan las métricas sin que se note."""

import numpy as np
import pandas as pd

from scripts.train_classifier import mejor_umbral, metricas, regla_manual, split_temporal


def _df(n_partidas: int = 10, jugadas: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": np.repeat([f"g{i}" for i in range(n_partidas)], jugadas),
            # g0 es la más antigua, g9 la más reciente (pero desordenadas en el DataFrame)
            "utc_datetime": np.repeat([f"2026.01.{i + 1:02d} 10:00:00" for i in range(n_partidas)], jugadas),
        }
    ).sample(frac=1, random_state=0)


def test_split_temporal_no_parte_partidas():
    train, test = split_temporal(_df())
    assert set(train.game_id).isdisjoint(test.game_id)
    assert len(train) + len(test) == 40


def test_split_temporal_prueba_son_las_mas_recientes():
    train, test = split_temporal(_df(), frac_test=0.2)
    assert set(test.game_id) == {"g8", "g9"}
    assert train.utc_datetime.max() < test.utc_datetime.min()


def test_regla_manual():
    X = pd.DataFrame({"hanging_mine_after_max": [0, 1, 3, 9, 0], "rival_mate_in_1": [0, 0, 0, 0, 1]})
    assert regla_manual(X).tolist() == [0, 0, 1, 1, 1]


def test_metricas_siempre_buena_no_detecta_nada():
    y = np.array([0] * 9 + [1])
    m = metricas(y, np.zeros_like(y))
    assert m["accuracy"] == 0.9 and m["recall"] == 0 and m["balanced_accuracy"] == 0.5


def test_mejor_umbral_separa_si_las_probabilidades_separan():
    y = np.array([0, 0, 0, 1, 1])
    prob = np.array([0.1, 0.2, 0.3, 0.7, 0.8])
    u = mejor_umbral(y, prob)
    assert 0.3 < u <= 0.7
