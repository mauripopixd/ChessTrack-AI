# Partida de ejemplo contra el coach (checkpoint de la Etapa 5B)

Generada con `python -m scripts.coach_demo`. Usuario simulado: Stockfish Skill Level 2; coach: nivel 4. Teoría de aperturas: sí. Trazas en LangSmith: sí.

Los comentarios tras un error los dispara el grafo solo; las preguntas son del usuario.

**1.** Tú: e4 — buena · Coach: e6  
**2.** Tú: c4 — buena · Coach: Nc6  
**3.** Tú: Ne2 — imprecisión (mejor Nc3) · Coach: Nf6  

**Pregunta:** ¿Cómo se llama esta apertura y cuál es la idea?

> **Coach** (openai/gpt-oss-120b, 5.1 s): La apertura es una **Defensa Francesa, Variante Nimzowitsch** (1.e4 e6 2.c4 Nc6) [1](https://github.com/lichess-org/chess-openings/blob/master/c.tsv).  
> 
> **Idea de las negras:** el caballo a c6 presiona la casilla d4 y prepara …d5 o …Bb4, desarrollando piezas sin bloquear el alfil de c8. Con …Nf6 atacan el peón e4 y buscan un rápido enroque.  
> 
> **Idea de las blancas:** con 2.c4 controlan d5 y b5, y el salto Ne2 mantiene el caballo fuera del pin Ng1‑f3‑Bb4 y permite que vaya a g3 o f4, apoyando d4 y el fianchetto del alfil. El plan típico es d4, Bg2, 0‑0 y presión central, mientras se protege el peón e4.
>
> [1] French Defense: Advance Variation — https://github.com/lichess-org/chess-openings/blob/master/c.tsv (CC0)

**4.** Tú: Nbc3 — buena · Coach: e5  
**5.** Tú: g3 — buena · Coach: Bc5  
**6.** Tú: Bh3 — imprecisión (mejor h3) · Coach: a6  
**7.** Tú: Bg2 — buena · Coach: h5  
**8.** Tú: h3 — buena · Coach: d6  
**9.** Tú: d3 — buena · Coach: h4  
**10.** Tú: gxh4 — buena · Coach: Nh7  

**Pregunta:** ¿Voy ganando o perdiendo, y qué plan me recomiendas?

> **Coach** (openai/gpt-oss-120b, 2.1 s): Según la evaluación de Stockfish estás **ligeramente peor** (≈‑0.7 peones) y la probabilidad de ganar es alrededor del 44 %.  
> 
> **Plan general:**  
> 1. **Rescatar el peón en h4** antes de que la dama negra lo capture. Una forma práctica es **Be3** (defiende h4 y desarrolla).  
> 2. **Consolidar el centro** con **d4** o **Nd5** cuando sea seguro; eso te da espacio y activa tus piezas.  
> 3. **Finalizar el desarrollo**: lleva el alfil de c1 a e3 o g5, el caballo de e2 a g3/f4 y enroca corto.  
> 4. **Contrajuego en el flanco‑dama**: una vez que el centro esté firme, busca romper con c5‑d5 o presionar la columna c.  
> 
> En resumen, defiende h4, completa tu desarrollo y luego lucha por el centro.

**11.** Tú: h5 — buena · Coach: Qh4  
**12.** Tú: Rf1 — buena · Coach: Bxh3  
**13.** Tú: Qb3 — error grave (mejor Bxh3) · Coach: Bxg2  
> **Coach** (openai/gpt-oss-120b, 1.4 s): Tu jugada Qb3 fue un error grave porque, tras ella, el rival pudo responder con Bxg2, Qxb7 o O‑O, dejando sin defensa tu peón en h5 y tu alfil en g2 y pasando de una ligera desventaja (‑1.5 peones) a una decisiva (‑7.6 peones). La idea correcta habría sido jugar Bxh3, que mantenía la presión y evitaba que esas amenazas se materializaran. En resumen, Qb3 abrió líneas que permitieron al rival ganar material y atacar tus piezas vulnerables.

**14.** Tú: Qxb7 — buena · Coach: Kd7  
**15.** Tú: Ng3 — buena · Coach: Rhb8  
**16.** Tú: Be3 — buena · Coach: Bd4  
**17.** Tú: Nd5 — buena · Coach: Rxb7  
**18.** Tú: Rg1 — buena · Coach: Rbb8  
**19.** Tú: O-O-O — buena · Coach: Bxb2+  
**20.** Tú: Kc2 — buena · Coach: Nd4+  

**Pregunta:** ¿Qué amenaza el coach con su última jugada?

> **Coach** (openai/gpt-oss-120b, 2.2 s): El último movimiento del coach fue **Nd4+**: el caballo de c6 saltó a d4 y da jaque al rey en c2.  
> 
> - **Amenaza inmediata:** el jaque obliga a que el rey se mueva, se bloquee o se capture el caballo.  
> - **Piezas atacadas:** desde d4 el caballo controla c2 (donde está tu rey), e2 (tu dama), f3 y b3, por lo que, si el jaque se resuelve sin eliminarlo, el caballo podrá capturar en **c2** o **e2** ganando material.  
> - **Objetivo a medio plazo:** mantener la presión central y abrir líneas contra tu rey, aprovechando que tu alfil en g2 está indefenso.  
> 
> En resumen, el caballo busca forzar una debilidad en tu posición y, si no lo eliminas, seguirá amenazando capturas decisivas.

**21.** Tú: Bxd4 — buena · Coach: Bxd4  
**22.** Tú: Rd2 — buena · Coach: Qh2  
**23.** Tú: Re1 — buena · Coach: Rb2+  
**24.** Tú: Kc1 — buena · Coach: Rxd2  
**25.** Tú: Kxd2 — buena · Coach: Bxf2  
**26.** Tú: Nf5 — buena · Coach: Rb8  
**27.** Tú: Ra1 — buena · Coach: Bf3  
**28.** Tú: Nb6+ — buena · Coach: Bxb6+  
**29.** Tú: Kc3 — buena · Coach: Bd4+  
**30.** Tú: Nxd4 — buena · Coach: exd4+  

**Pregunta:** ¿Cuál ha sido mi peor jugada hasta ahora y por qué?

> **Coach** (openai/gpt-oss-120b, 19.1 s): Tu peor jugada ha sido **13. Qb3**. Con esa jugada entregaste la dama a un ataque doble: el alfil negro en c5 podía capturar en g1 y, tras Bxh3, la torre y el alfil blancos quedaron sin defensa. Además, al mover la dama abandonaste la defensa del peón h5 y del alfil g2, permitiendo que el rival ganara material rápidamente (capturó en g2 y luego tomó la dama). En la evaluación, esa jugada pasó de una ligera desventaja (‑1,5 peones) a una pérdida decisiva (‑7,6 peones), cambiando la probabilidad de ganar de ~37 % a menos del 6 %. En resumen, Qb3 abrió líneas que el rival explotó para ganar piezas y dar jaque mate.

**31.** Tú: Kxd4 — buena · Coach: Qf2+  
**32.** Tú: Kd5 — buena · Coach: Rb5+  
**33.** Tú: cxb5 — buena · Coach: Qc5#  

## Resumen

- Resultado: 0-1 (checkmate)
- Jugadas del usuario: 33 (buena 30, imprecisión 2, error grave 1)
- Turnos con LLM: 5 · mediana 2.2 s · openai/gpt-oss-120b: 5
- Turnos sin LLM (jugada buena o imprecisión): 32

## PGN

```
[Event "ChessTrack AI · partida contra el coach"]
[Site "?"]
[Date "2026.11.21"]
[Round "?"]
[White "Tú"]
[Black "Coach (nivel 4)"]
[Result "0-1"]

1. e4 e6 2. c4 Nc6 3. Ne2 Nf6 4. Nbc3 e5 5. g3 Bc5 6. Bh3 a6 7. Bg2 h5 8. h3 d6 9. d3 h4 10. gxh4 Nh7 11. h5 Qh4 12. Rf1 Bxh3 13. Qb3 Bxg2 14. Qxb7 Kd7 15. Ng3 Rhb8 16. Be3 Bd4 17. Nd5 Rxb7 18. Rg1 Rbb8 19. O-O-O Bxb2+ 20. Kc2 Nd4+ 21. Bxd4 Bxd4 22. Rd2 Qh2 23. Re1 Rb2+ 24. Kc1 Rxd2 25. Kxd2 Bxf2 26. Nf5 Rb8 27. Ra1 Bf3 28. Nb6+ Bxb6+ 29. Kc3 Bd4+ 30. Nxd4 exd4+ 31. Kxd4 Qf2+ 32. Kd5 Rb5+ 33. cxb5 Qc5# 0-1
```
