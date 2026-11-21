# Clasificador de jugadas · Random Forest

> Generado por `python -m scripts.train_classifier --dataset dataset_all.csv`. No editar a mano.

**Pregunta:** ¿es esta jugada un error (*error* o *error grave* según Stockfish), mirando solo el
tablero, **sin motor**? Las variables están en `app/ml/features.py`.

## Datos

- 6,099 partidas, 456,921 jugadas; 10.0% son errores.
- División **temporal por partidas**: entrenamiento con 4,879 partidas
  (364,368 jugadas), prueba con las 1,220 más recientes (92,553 jugadas).
- Umbral de decisión 0.52, elegido maximizando F1 en una validación **dentro** del
  entrenamiento (la prueba no se usa para nada hasta el final).

## Resultados en prueba (clase positiva = error)

| Modelo | Precisión | Recall | F1 | Acierto equilibrado | PR-AUC |
|---|---|---|---|---|---|
| siempre «buena» | 0.000 | 0.000 | 0.000 | 0.500 | — |
| regla manual | 0.158 | 0.157 | 0.158 | 0.533 | — |
| random forest (umbral 0.52) | 0.235 | 0.534 | 0.326 | 0.673 | 0.266 |
| random forest · solo mis jugadas | 0.237 | 0.554 | 0.332 | 0.682 | 0.270 |

- **Precisión:** de las jugadas que el modelo marca como error, cuántas lo son de verdad.
- **Recall:** de los errores reales, cuántos detecta.
- **PR-AUC:** calidad de la probabilidad en todos los umbrales. Con un 10% de
  errores, un modelo al azar sacaría unos 0.10.
- El acierto simple **no sirve**: "siempre buena" acierta el
  90% sin detectar ni un error.

Matriz de confusión del Random Forest en prueba: 4,815 errores detectados, 4,203 errores no
detectados, 15,715 falsas alarmas, 67,820 jugadas buenas bien clasificadas.

## ¿Qué errores detecta?

Proporción de jugadas que el modelo marca como error, según la etiqueta de Stockfish:

| Etiqueta de Stockfish | Marcadas como error |
|---|---|
| buena | 16.9% |
| imprecision | 35.7% |
| error | 49.2% |
| error_grave | 59.2% |

## Variables más importantes

Importancia por permutación en prueba: cuánto empeora la PR-AUC si se baraja esa variable.

| Variable | Importancia |
|---|---|
| `material_diff` | 0.0294 |
| `captured_value` | 0.0285 |
| `hanging_mine_after_max` | 0.0265 |
| `rival_captures` | 0.0247 |
| `ply` | 0.0230 |
| `legal_moves` | 0.0170 |
| `hanging_mine_after` | 0.0168 |
| `clock_after` | 0.0126 |
| `time_spent` | 0.0108 |
| `free_capture_missed` | 0.0084 |
| `is_capture` | 0.0076 |
| `hanging_mine_delta` | 0.0060 |
