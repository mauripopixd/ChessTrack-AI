# RAG de aperturas · calidad de la búsqueda

> Generado por `python -m scripts.eval_retrieval`. No editar a mano.

Modelo de embeddings `BAAI/bge-m3` (multilingüe), 20 preguntas en español sobre un corpus en
inglés. Un acierto es un fragmento de la apertura correcta (o de una variante suya) entre los
5 primeros. Tiempo de búsqueda: mediana 20 ms por pregunta.

**acierto@1 75% · acierto@3 90% · acierto@5 95% · MRR 0.83**

| Pregunta | Posición de la fuente correcta | Primer resultado |
|---|---|---|
| ¿Cuál es la idea principal de la Defensa Siciliana? | 1 | Sicilian Defense · `1. e4 c5` (wikibooks) |
| ¿Qué busca el negro con la Defensa Francesa? | 1 | French Defense · `1. e4 e6` (wikibooks) |
| ¿Por qué la Defensa Caro-Kann se considera sólida? | 1 | Caro-Kann Defense · `1. e4 c6 2. d4 d5 3. Nc3 dxe4 4. Nxe4 Nf6 5. Qd3 e5` (wikibooks) |
| ¿Qué pasa en el Gambito de Dama si el negro acepta el peón? | ✗ | Petrov's Defense: Stafford Gambit Accepted · `1. e4 e5 2. Nf3 Nf6 3. Nxe5 Nc6 4. Nxc6 dxc6 5. d3 Bc5` (wikibooks) |
| ¿Qué jugadas definen la Variante Najdorf de la Siciliana? | 1 | Sicilian Defense: Najdorf Variation · `1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6` (wikibooks) |
| ¿Cuál es el plan de las blancas en la Apertura Española (Ruy López)? | 1 | Ruy Lopez · `1. e4 e5 2. Nf3 Nc6 3. Bb5` (wikibooks) |
| ¿Qué ofrece el blanco en el Gambito de Rey y por qué? | 1 | King's Gambit Accepted · `1. e4 e5 2. f4 exf4` (wikibooks) |
| ¿Qué ideas tiene el negro en la Defensa India de Rey? | 1 | Indian Defense: West Indian Defense · `1. d4 Nf6 2. c4 g6` (wikibooks) |
| ¿En qué consiste la Defensa Escandinava? | 1 | Scandinavian Defense · `1. e4 d5` (wikibooks) |
| ¿Por qué 1. Na3 se considera una mala primera jugada? | 4 | Anderssen's Opening · `1. a3 a6` (wikibooks) |
| ¿Qué es la Apertura Inglesa? | 2 | — · `` (wikibooks) |
| ¿Qué es la Defensa Alekhine? | 1 | Alekhine Defense · `1. e4 Nf6` (wikibooks) |
| ¿Qué es la Defensa Holandesa? | 1 | Dutch Defense · `1. d4 f5 2. c4` (wikibooks) |
| ¿Qué es el Gambito Evans? | 1 | Italian Game: Evans Gambit · `1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4` (wikibooks) |
| ¿Qué es la Defensa Pirc? | 1 | Pirc Defense · `1. e4 d6` (wikibooks) |
| ¿Qué es el Gambito Budapest? | 2 | Hungarian Opening · `1. g3` (wikibooks) |
| ¿Qué es la Defensa Petrov o Rusa? | 1 | Petrov's Defense · `1. e4 e5 2. Nf3 Nf6` (wikibooks) |
| ¿Qué es el Ataque Fried Liver (Fegatello)? | 1 | Italian Game: Two Knights Defense, Fried Liver Attack · `1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7 Kxf7 7. Qf3 Ke6 8. Nc3` (wikibooks) |
| ¿Cuál es la idea del Sistema Londres? | 1 | Indian Defense: Accelerated London System · `1. d4 Nf6 2. Bf4 d5 3. e3 e6 4. Nf3` (wikibooks) |
| ¿Qué es la Defensa Eslava? | 3 | Sicilian Defense: Dragon Variation, Yugoslav Attack, Early Deviations · `1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 g6 6. Be3 Bg7 7. f3` (wikibooks) |
