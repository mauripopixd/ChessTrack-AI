"""Entrena el clasificador de jugadas (Random Forest) y escribe su informe.

    python -m scripts.train_classifier                                   # dataset.csv
    python -m scripts.train_classifier --dataset data/analysis/dataset_all.csv

- Objetivo principal: ¿la jugada es un ERROR (error o error grave según Stockfish)?
  Es binario: un coach necesita sobre todo avisar de los errores; separar "imprecisión"
  de "buena" con 5 puntos de probabilidad es ruido para un modelo sin motor.
- División TEMPORAL por partidas: entrena con las más antiguas y evalúa con el 20 % más
  reciente. Así no se mezclan jugadas de una misma partida entre entrenamiento y prueba,
  y se mide lo que importa: juzgar partidas futuras.
- Se compara con dos líneas base: "siempre buena" y una regla escrita a mano.

Guarda el modelo en models/ (no se versiona) y el informe en docs/modelo_rf.md.
"""

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ml.features import FEATURES

RAIZ = Path(__file__).resolve().parent.parent
ERRORES = {"error", "error_grave"}
SEMILLA = 42


def split_temporal(df: pd.DataFrame, frac_test: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Las partidas más recientes (por fecha) van a prueba; nunca se parte una partida."""
    fechas = df.groupby("game_id").utc_datetime.first().sort_values()
    corte = int(len(fechas) * (1 - frac_test))
    test_ids = set(fechas.index[corte:])
    es_test = df.game_id.isin(test_ids)
    return df[~es_test], df[es_test]


def regla_manual(X: pd.DataFrame) -> np.ndarray:
    """Línea base: 'error' si tras mover queda colgando una pieza (≥ alfil/caballo) o se
    permite mate en 1. Es lo primero que miraría un jugador humano."""
    return ((X.hanging_mine_after_max >= 3) | (X.rival_mate_in_1 == 1)).astype(int).to_numpy()


def metricas(y: np.ndarray, pred: np.ndarray, prob: np.ndarray | None = None) -> dict[str, float]:
    m = {
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "accuracy": float((y == pred).mean()),
    }
    if prob is not None:
        m["roc_auc"] = roc_auc_score(y, prob)
        m["pr_auc"] = average_precision_score(y, prob)
    return {k: round(float(v), 3) for k, v in m.items()}


def mejor_umbral(y: np.ndarray, prob: np.ndarray) -> float:
    """Umbral de probabilidad que maximiza F1 en los datos que se le pasen."""
    umbrales = np.linspace(0.05, 0.95, 91)
    f1s = [f1_score(y, prob >= u, zero_division=0) for u in umbrales]
    return float(umbrales[int(np.argmax(f1s))])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", type=Path, default=RAIZ / "data" / "analysis" / "dataset.csv")
    parser.add_argument("--model-out", type=Path, default=RAIZ / "models" / "clasificador_rf.joblib")
    parser.add_argument("--report", type=Path, default=RAIZ / "docs" / "modelo_rf.md")
    parser.add_argument("--trees", type=int, default=300)
    args = parser.parse_args()
    inicio = time.perf_counter()

    df = pd.read_csv(args.dataset)
    df["y"] = df.label.isin(ERRORES).astype(int)
    train, test = split_temporal(df)
    # Validación dentro de train (también temporal) para elegir el umbral sin mirar test.
    sub_train, valid = split_temporal(train, frac_test=0.2)
    print(
        f"{df.game_id.nunique()} partidas · train {len(train):,} jugadas · test {len(test):,} · "
        f"errores: {df.y.mean():.1%}",
        flush=True,
    )

    def rf() -> RandomForestClassifier:
        return RandomForestClassifier(
            n_estimators=args.trees,
            min_samples_leaf=20,  # hojas no diminutas: evita memorizar jugadas sueltas
            max_features="sqrt",
            class_weight="balanced_subsample",  # los errores son ~1 de cada 10: que pesen más
            n_jobs=-1,
            random_state=SEMILLA,
        )

    # 1) Umbral elegido en validación (sin tocar test).
    modelo_val = rf().fit(sub_train[FEATURES], sub_train.y)
    umbral = mejor_umbral(valid.y.to_numpy(), modelo_val.predict_proba(valid[FEATURES])[:, 1])
    # 2) Modelo final con todo train.
    modelo = rf().fit(train[FEATURES], train.y)
    prob = modelo.predict_proba(test[FEATURES])[:, 1]
    pred = (prob >= umbral).astype(int)
    y = test.y.to_numpy()

    resultados = {
        "siempre «buena»": metricas(y, np.zeros_like(y)),
        "regla manual": metricas(y, regla_manual(test)),
        f"random forest (umbral {umbral:.2f})": metricas(y, pred, prob),
    }
    solo_mias = test.is_user.to_numpy(dtype=bool)
    resultados["random forest · solo mis jugadas"] = metricas(y[solo_mias], pred[solo_mias], prob[solo_mias])

    # Importancia por permutación en test (más honesta que la de impureza del árbol).
    muestra = test.sample(min(len(test), 20_000), random_state=SEMILLA)
    imp = permutation_importance(
        modelo, muestra[FEATURES], muestra.y, scoring="average_precision",
        n_repeats=5, random_state=SEMILLA, n_jobs=-1,
    )  # fmt: skip
    importancia = pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False).round(4)

    # Recall por etiqueta original: ¿detecta más los errores graves que los normales?
    test_eval = test.assign(pred=pred)
    por_etiqueta = (
        test_eval.groupby("label").pred.mean().reindex(["buena", "imprecision", "error", "error_grave"])
    )
    cm = confusion_matrix(y, pred)

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modelo": modelo, "features": FEATURES, "umbral": umbral}, args.model_out, compress=3)
    _informe(args.report, df, train, test, resultados, importancia, por_etiqueta, cm, umbral, args)
    (args.report.with_suffix(".json")).write_text(
        json.dumps({"umbral": umbral, "resultados": resultados}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(resultados, indent=2, ensure_ascii=False))
    print(f"Listo en {time.perf_counter() - inicio:.0f} s → {args.report.name}, {args.model_out.name}")
    return 0


def _informe(ruta, df, train, test, resultados, importancia, por_etiqueta, cm, umbral, args) -> None:
    filas = "\n".join(
        f"| {nombre} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
        f"{m['balanced_accuracy']:.3f} | {f'{m["pr_auc"]:.3f}' if 'pr_auc' in m else '—'} |"
        for nombre, m in resultados.items()
    )
    top = "\n".join(f"| `{f}` | {v:.4f} |" for f, v in importancia.head(12).items())
    etiquetas = "\n".join(f"| {e} | {v:.1%} |" for e, v in por_etiqueta.items())
    (tn, fp), (fn, tp) = cm
    texto = f"""# Clasificador de jugadas · Random Forest

> Generado por `python -m scripts.train_classifier --dataset {args.dataset.name}`. No editar a mano.

**Pregunta:** ¿es esta jugada un error (*error* o *error grave* según Stockfish), mirando solo el
tablero, **sin motor**? Las variables están en `app/ml/features.py`.

## Datos

- {df.game_id.nunique():,} partidas, {len(df):,} jugadas; {df.y.mean():.1%} son errores.
- División **temporal por partidas**: entrenamiento con {train.game_id.nunique():,} partidas
  ({len(train):,} jugadas), prueba con las {test.game_id.nunique():,} más recientes ({len(test):,} jugadas).
- Umbral de decisión {umbral:.2f}, elegido maximizando F1 en una validación **dentro** del
  entrenamiento (la prueba no se usa para nada hasta el final).

## Resultados en prueba (clase positiva = error)

| Modelo | Precisión | Recall | F1 | Acierto equilibrado | PR-AUC |
|---|---|---|---|---|---|
{filas}

- **Precisión:** de las jugadas que el modelo marca como error, cuántas lo son de verdad.
- **Recall:** de los errores reales, cuántos detecta.
- **PR-AUC:** calidad de la probabilidad en todos los umbrales. Con un {test.y.mean():.0%} de
  errores, un modelo al azar sacaría unos {test.y.mean():.2f}.
- El acierto simple **no sirve**: "siempre buena" acierta el
  {resultados["siempre «buena»"]["accuracy"]:.0%} sin detectar ni un error.

Matriz de confusión del Random Forest en prueba: {tp:,} errores detectados, {fn:,} errores no
detectados, {fp:,} falsas alarmas, {tn:,} jugadas buenas bien clasificadas.

## ¿Qué errores detecta?

Proporción de jugadas que el modelo marca como error, según la etiqueta de Stockfish:

| Etiqueta de Stockfish | Marcadas como error |
|---|---|
{etiquetas}

## Variables más importantes

Importancia por permutación en prueba: cuánto empeora la PR-AUC si se baraja esa variable.

| Variable | Importancia |
|---|---|
{top}
"""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
