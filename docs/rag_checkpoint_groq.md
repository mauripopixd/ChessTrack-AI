# Checkpoint Etapa 5A · 10 preguntas de teoría con fuentes

> Generado por `python -m scripts.eval_rag --provider groq`. No editar a mano.

Modelo: groq · openai/gpt-oss-120b. Fuentes: Wikibooks *Chess Opening Theory* (CC BY-SA 4.0)
y Lichess *chess-openings* (CC0), recuperadas con `bge-m3` (6 fragmentos por pregunta).

**9/10 preguntas superan las tres comprobaciones · latencia mediana 1.8 s**

Comprobaciones automáticas por respuesta: cita al menos una fuente · no cita números
inexistentes · alguna fuente citada es de la apertura preguntada. Leer las respuestas sigue
siendo necesario: las comprobaciones no verifican que cada frase diga lo mismo que su fuente.

### 1. ¿Cuál es la idea principal de la Defensa Siciliana?

La Defensa Siciliana es una apertura contra‑ataque y asimétrica: al jugar 1…c5 Black controla la casilla d4 con un peón de flanco, intercambia su peón c por el peón central d de White y queda con dos peones centrales frente a uno, lo que le permite buscar …d5 más adelante y explotar la columna c si se abre [1]. Después de 2 Nf3 White suele seguir con 3 d4 para abrir el centro, mientras que Black debe desarrollar sus piezas (normalmente …d6 para liberar el alfil de casillas claras y controlar e5) antes de completar su desarrollo [4][5]. En esencia, la idea es obtener juego activo y contrajuego en el centro y en la c‑file.

  - [1] [1. e4/1...c5](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...c5) — wikibooks, CC BY-SA 4.0
  - [4] [1. e4/1...c5/2. Nf3](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...c5/2._Nf3) — wikibooks, CC BY-SA 4.0
  - [5] [1. e4/1...c5/2. Nf3/2...d6/3. d4](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...c5/2._Nf3/2...d6/3._d4) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 1.9 s · groq
### 2. ¿Qué busca el negro con la Defensa Francesa?

El negro busca ganar espacio en el centro, especialmente en la casilla d5. Para ello primero juega …e6, que le permite apoyar …d5 sin que las blancas lo capturen inmediatamente, y así poder recapturar y mantener un peón en d5 [1].

  - [1] [1. e4/1...e6](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...e6) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 8.8 s · groq
### 3. ¿Por qué la Defensa Caro-Kann se considera sólida?

La Defensa Caro‑Kann se considera una apertura sólida porque Black responde a 1.e4 con 1…c6, preparando …d5 y creando una estructura de peones muy resistente. Según Wikibooks, “su reputación es la misma hoy: una respuesta sólida y defensiva a e4, aunque no tan dinámica como otras” y es elegida por jugadores que quieren evitar la gran teoría de la Siciliana [2]. Además, el plan de …c6 y …d5 permite a Black controlar la casilla c4 y proteger el punto f7, reduciendo las amenazas típicas del juego abierto [3]. Esta configuración evita bloquear al propio alfil de casillas negras y mantiene una posición segura para el rey, lo que refuerza su carácter “sólido”. [2][3]

  - [2] [1. e4/1...c6](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...c6) — wikibooks, CC BY-SA 4.0
  - [3] [1. e4/1...c6](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...c6) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 1.8 s · groq
### 4. ¿Qué pasa en el Gambito de Dama si el negro acepta el peón?

No dispongo de fuentes que describan la línea del Gambito de Dama en la que las negras aceptan el peón, por lo que no puedo responder a la pregunta con la información requerida.

  - (sin citas)

❌ cita fuentes · ✅ sin citas inventadas · ❌ cita la apertura correcta · 1.0 s · groq
### 5. ¿Qué jugadas definen la Variante Najdorf de la Siciliana?

La Variante Najdorf de la Defensa Siciliana se define por la secuencia de jugadas: 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6 [1][6]

  - [1] [1. e4/1...c5/2. Nf3/2...d6/3. d4/3...cxd4/4. Nxd4/4...Nf6/5. Nc3/5...a6](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...c5/2._Nf3/2...d6/3._d4/3...cxd4/4._Nxd4/4...Nf6/5._Nc3/5...a6) — wikibooks, CC BY-SA 4.0
  - [6] [1. e4/1...c5/2. Nf3/2...d6/3. d4/3...cxd4/4. Nxd4/4...Nf6/5. Nc3/5...a6/6. Bg5](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...c5/2._Nf3/2...d6/3._d4/3...cxd4/4._Nxd4/4...Nf6/5._Nc3/5...a6/6._Bg5) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 5.8 s · groq
### 6. ¿Cuál es el plan de las blancas en la Apertura Española (Ruy López)?

El plan típico de las blancas en la Apertura Española es desarrollar rápidamente sus piezas, enrocarse y preparar el avance central con c3 y d4 para obtener una mayoría de peones en el centro. Tras Bb5 las blancas buscan controlar e5, completar el desarrollo del alfil y la torre (Re1) y, una vez el rey está seguro, lanzar c3 para dar salida al alfil de b3 y luego d4 para abrir el centro y aprovechar su ventaja de espacio [1][5].

  - [1] [1. e4/1...e5/2. Nf3/2...Nc6/3. Bb5](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...e5/2._Nf3/2...Nc6/3._Bb5) — wikibooks, CC BY-SA 4.0
  - [5] [1. e4/1...e5/2. Nf3/2...Nc6/3. Bb5/3...a6/4. Ba4/4...Nf6/5. O-O/5...Be7/6. Re1/6...b5/7. Bb3/7...d6](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...e5/2._Nf3/2...Nc6/3._Bb5/3...a6/4._Ba4/4...Nf6/5._O-O/5...Be7/6._Re1/6...b5/7._Bb3/7...d6) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 1.7 s · groq
### 7. ¿Qué ofrece el blanco en el Gambito de Rey y por qué?

En el Gambito de Rey, tras 1.e4 e5 2.f4, el blanco sacrifica el peón de f (f4) para que Black lo capture (exf4). Con ese sacrificio, blanco busca abrir la columna f, acelerar su desarrollo y crear presión sobre el centro y el rey negro, obteniendo iniciativa a cambio del peón [1].

  - [1] [1. e4/1...e5/2. f4/2...exf4](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...e5/2._f4/2...exf4) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 2.9 s · groq
### 8. ¿Qué ideas tiene el negro en la Defensa India de Rey?

En la Defensa India de Rey, Negro primero juega 2…g6 para fianchettoar su alfil de casillas negras en Bg7, controlando la larga diagonal y reforzando la defensa del rey tras el enroque [2]. El plan típico es atacar en el flanco de rey con rupturas de peón …e5 y …f5, aunque también puede buscar contrajuego en el centro o en el flanco de dama con …c5 y …b5 [2]. Negro mantiene una estructura hipermoderna: permite que Blancas ocupen el centro con peones y piezas, para luego desafiarlo con esas rupturas. En la línea ortodoxa, después de 4.e4 d6 5.Nf3 O‑O 6.Be2 e5, Negro presiona el centro y prepara …Nc6 ‑ …Ne7‑f5 para lanzar un ataque al rey blanco [5].

  - [2] [1. d4/1...Nf6/2. c4/2...g6](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._d4/1...Nf6/2._c4/2...g6) — wikibooks, CC BY-SA 4.0
  - [5] [1. d4/1...Nf6/2. c4/2...g6/3. Nc3/3...Bg7/4. e4/4...d6/5. Nf3/5...O-O/6. Be2/6...e5/7. O-O](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._d4/1...Nf6/2._c4/2...g6/3._Nc3/3...Bg7/4._e4/4...d6/5._Nf3/5...O-O/6._Be2/6...e5/7._O-O) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 1.6 s · groq
### 9. ¿En qué consiste la Defensa Escandinava?

La Defensa Escandinava se inicia con 1.e4 d5, donde las negras atacan inmediatamente el centro de blancas y buscan cambiar el peón central, aunque ello implique desarrollar antes a la dama. Tras 2.exd5, la línea clásica es 2…Qxd5, obligando a 3.Nc3 a ganar tempo a la dama, que suele retroceder a a5 u otra casilla. La alternativa moderna es 2…Nf6, retrasando la recuperación del peón y permitiendo a las negras jugar …Nxd5 o …d4 según la continuación de blancas. En ambos casos el objetivo es desestabilizar el centro blanco y obtener juego activo a cambio de la pérdida temporal de un peón. [1][4]

  - [1] [1. e4/1...d5](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...d5) — wikibooks, CC BY-SA 4.0
  - [4] [1. e4/1...d5/2. exd5](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4/1...d5/2._exd5) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 1.2 s · groq
### 10. ¿Por qué 1. Na3 se considera una mala primera jugada?

1. Na3 ? ? es una mala primera jugada porque coloca al caballo en el borde del tablero, donde tiene muy poca influencia sobre el centro y no contribuye al desarrollo de piezas. Además, no controla casillas clave y permite a negras ocupar el centro libremente con ...e5 o ...d5, obteniendo una ventaja de espacio y desarrollo. En resumen, el movimiento “pierde tiempo” y entrega a negras la iniciativa central. [4]

  - [4] [1. Na3](https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._Na3) — wikibooks, CC BY-SA 4.0

✅ cita fuentes · ✅ sin citas inventadas · ✅ cita la apertura correcta · 1.2 s · groq
