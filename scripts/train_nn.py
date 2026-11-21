"""Entrena la red del clasificador de jugadas (PyTorch) y la compara con el Random Forest.

    python -m scripts.train_nn --dataset data/analysis/dataset_all.csv

Misma tarea, misma división temporal y mismas métricas que scripts/train_classifier.py,
así que los números se comparan directamente con docs/modelo_rf.md. Entrena dos variantes:

- "solo tablero": la red recibe únicamente el tablero (26 × 8 × 8);
- "tablero + variables": además, las 28 variables escritas a mano.

Usa la GPU si hay (CUDA); en CPU funciona pero tarda mucho más. Guarda los modelos en
models/ (no versionado) y el informe en docs/modelo_nn.md.
"""

import argparse
import copy
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score

from app.ml.board_tensor import encode_game
from app.ml.features import FEATURES
from app.ml.net import MoveClassifier
from scripts.train_classifier import ERRORES, SEMILLA, mejor_umbral, metricas, split_temporal

RAIZ = Path(__file__).resolve().parent.parent
LOTE = 2048


def cargar_tableros(df: pd.DataFrame, cache: Path, workers: int) -> np.ndarray:
    """Tensores de todas las jugadas, en el mismo orden que `df` (cacheados en disco)."""
    if cache.exists():
        tableros = np.load(cache, mmap_mode="r")
        if tableros.shape[0] == len(df):
            return np.array(tableros)  # copia escribible en memoria (el mmap es de solo lectura)
    partidas = [g.uci.tolist() for _, g in df.groupby("game_id", sort=False)]
    with ProcessPoolExecutor(workers) as pool:
        tableros = np.concatenate(list(pool.map(encode_game, partidas, chunksize=50)))
    assert tableros.shape[0] == len(df), "tableros y filas desalineados"
    np.save(cache, tableros)
    return tableros


def predecir(red, X, S, idx, dev) -> np.ndarray:
    red.eval()
    salida = []
    with torch.no_grad(), torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
        for i in range(0, len(idx), LOTE * 4):
            b = idx[i : i + LOTE * 4]
            salida.append(torch.sigmoid(red(X[b].float(), S[b]).float()))
    return torch.cat(salida).cpu().numpy()


def entrenar(nombre, n_escalares, X, S, Y, i_train, i_valid, dev, epocas, paciencia):
    torch.manual_seed(SEMILLA)
    red = MoveClassifier(n_escalares=n_escalares).to(dev)
    positivos = Y[i_train].sum().item()
    # pos_weight: un error "pesa" tanto como ~9 jugadas buenas (hay 1 error por cada 9).
    perdida_fn = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor((len(i_train) - positivos) / positivos, device=dev)
    )
    opt = torch.optim.AdamW(red.parameters(), lr=1e-3, weight_decay=1e-4)
    planificador = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="max", factor=0.3, patience=1)
    y_valid = Y[i_valid].cpu().numpy()
    mejor, mejor_estado, sin_mejora, historia = -1.0, None, 0, []
    generador = torch.Generator(device=dev).manual_seed(SEMILLA)

    for epoca in range(1, epocas + 1):
        red.train()
        inicio = time.perf_counter()
        orden = i_train[torch.randperm(len(i_train), device=dev, generator=generador)]
        total = 0.0
        for i in range(0, len(orden), LOTE):
            b = orden[i : i + LOTE]
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                perdida = perdida_fn(red(X[b].float(), S[b]).float(), Y[b])
            opt.zero_grad(set_to_none=True)
            perdida.backward()
            opt.step()
            total += perdida.item() * len(b)
        pr_auc = average_precision_score(y_valid, predecir(red, X, S, i_valid, dev))
        planificador.step(pr_auc)
        historia.append(
            {"epoca": epoca, "perdida": round(total / len(orden), 4), "pr_auc_valid": round(float(pr_auc), 4)}
        )
        print(
            f"  [{nombre}] época {epoca}: pérdida {total / len(orden):.4f} · PR-AUC valid {pr_auc:.4f} · "
            f"{time.perf_counter() - inicio:.0f} s",
            flush=True,
        )
        if pr_auc > mejor:
            mejor, mejor_estado, sin_mejora = pr_auc, copy.deepcopy(red.state_dict()), 0
        else:
            sin_mejora += 1
            if sin_mejora >= paciencia:  # early stopping
                break
    red.load_state_dict(mejor_estado)
    return red, historia


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", type=Path, default=RAIZ / "data" / "analysis" / "dataset_all.csv")
    parser.add_argument("--report", type=Path, default=RAIZ / "docs" / "modelo_nn.md")
    parser.add_argument("--epocas", type=int, default=20)
    parser.add_argument("--paciencia", type=int, default=3)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    inicio = time.perf_counter()
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Dispositivo: {torch.cuda.get_device_name(0) if dev.type == 'cuda' else 'CPU'}", flush=True)

    df = pd.read_csv(args.dataset).sort_values(["game_id", "ply"], kind="stable").reset_index(drop=True)
    df["y"] = df.label.isin(ERRORES).astype(int)
    train, test = split_temporal(df)
    sub_train, valid = split_temporal(train, frac_test=0.2)
    tableros = cargar_tableros(df, args.dataset.with_name(f"boards_{args.dataset.stem}.npy"), args.workers)
    print(f"Tableros: {tableros.shape} ({tableros.nbytes / 1e6:.0f} MB)", flush=True)

    # Variables escalares normalizadas con media y desviación del ENTRENAMIENTO (sin mirar test).
    media, desv = sub_train[FEATURES].mean(), sub_train[FEATURES].std().replace(0, 1)
    escalares = ((df[FEATURES] - media) / desv).to_numpy(np.float32)

    X = torch.from_numpy(tableros).to(dev)
    S = torch.from_numpy(escalares).to(dev)
    Y = torch.from_numpy(df.y.to_numpy(np.float32)).to(dev)
    a_idx = lambda parte: torch.from_numpy(parte.index.to_numpy().copy()).to(dev)  # noqa: E731
    i_sub, i_valid, i_test = a_idx(sub_train), a_idx(valid), a_idx(test)
    y_valid, y_test = valid.y.to_numpy(), test.y.to_numpy()

    resultados, historias, umbrales, n_param = {}, {}, {}, {}
    for nombre, n_esc in [("red · solo tablero", 0), ("red · tablero + variables", len(FEATURES))]:
        red, historias[nombre] = entrenar(
            nombre, n_esc, X, S, Y, i_sub, i_valid, dev, args.epocas, args.paciencia
        )
        umbral = mejor_umbral(y_valid, predecir(red, X, S, i_valid, dev))
        prob = predecir(red, X, S, i_test, dev)
        pred = (prob >= umbral).astype(int)
        resultados[f"{nombre} (umbral {umbral:.2f})"] = metricas(y_test, pred, prob)
        umbrales[nombre] = umbral
        n_param[nombre] = sum(p.numel() for p in red.parameters())
        por_etiqueta = test.assign(pred=pred).groupby("label").pred.mean()
        resultados[f"{nombre} (umbral {umbral:.2f})"]["detecta_error_grave"] = round(
            float(por_etiqueta.get("error_grave", 0)), 3
        )
        ruta = RAIZ / "models" / f"clasificador_nn_{'tablero' if n_esc == 0 else 'hibrido'}.pt"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "estado": red.state_dict(),
                "n_escalares": n_esc,
                "umbral": umbral,
                "features": FEATURES,
                "media": media.to_dict(),
                "desv": desv.to_dict(),
            },
            ruta,
        )

    rf = json.loads((RAIZ / "docs" / "modelo_rf.json").read_text(encoding="utf-8"))
    _informe(args.report, df, sub_train, valid, test, resultados, rf, historias, n_param, dev, inicio)
    args.report.with_suffix(".json").write_text(
        json.dumps({"umbrales": umbrales, "resultados": resultados, "historias": historias}, indent=2,
                   ensure_ascii=False),
        encoding="utf-8",
    )  # fmt: skip
    print(json.dumps(resultados, indent=2, ensure_ascii=False))
    print(f"Listo en {(time.perf_counter() - inicio) / 60:.1f} min → {args.report.name}")
    return 0


def _num(m: dict, clave: str) -> str:
    return f"{m[clave]:.3f}" if clave in m else "—"


def _informe(ruta, df, sub_train, valid, test, resultados, rf, historias, n_param, dev, inicio) -> None:
    rf_nombre, rf_m = next((k, v) for k, v in rf["resultados"].items() if k.startswith("random forest ("))
    filas_tabla = [("regla manual", rf["resultados"]["regla manual"]), (rf_nombre, rf_m), *resultados.items()]
    filas = "\n".join(
        f"| {n} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
        f"{_num(m, 'pr_auc')} | {_num(m, 'roc_auc')} |"
        for n, m in filas_tabla
    )
    curvas = "\n\n".join(
        f"**{n}** ({n_param[n]:,} parámetros)\n\n| Época | Pérdida | PR-AUC validación |\n|---|---|---|\n"
        + "\n".join(f"| {h['epoca']} | {h['perdida']:.4f} | {h['pr_auc_valid']:.4f} |" for h in hist)
        for n, hist in historias.items()
    )
    dispositivo = torch.cuda.get_device_name(0) if dev.type == "cuda" else "CPU"
    texto = f"""# Clasificador de jugadas · red neuronal (PyTorch)

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
- Pérdida BCE con `pos_weight` (hay 1 error por cada ~9 jugadas buenas), AdamW, bf16 en {dispositivo}.
- **Early stopping** con la PR-AUC de validación: {len(sub_train):,} jugadas de entrenamiento y
  {len(valid):,} de validación, ambas dentro del entrenamiento del RF. La prueba son las mismas
  {len(test):,} jugadas que en `modelo_rf.md`.

## Resultados en prueba (clase positiva = error)

| Modelo | Precisión | Recall | F1 | PR-AUC | ROC-AUC |
|---|---|---|---|---|---|
{filas}

Al azar, la PR-AUC sería unos {test.y.mean():.2f}.

## Entrenamiento

{curvas}

Tiempo total: {(time.perf_counter() - inicio) / 60:.1f} min
(incluye codificar los tableros si no estaban en caché).
"""
    ruta.write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
