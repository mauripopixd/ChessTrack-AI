# Partida de ejemplo contra el coach (checkpoint de la Etapa 5B)

Generada con `python -m scripts.coach_demo`. Usuario simulado: Stockfish Skill Level 2; coach: nivel 4. Teoría de aperturas: sí. Trazas en LangSmith: no.

Los comentarios tras un error los dispara el grafo solo; las preguntas son del usuario.

**1.** Tú: Nf3 — buena · Coach: d5  
**2.** Tú: g3 — buena · Coach: Nf6  
**3.** Tú: Bg2 — buena · Coach: c6  

**Pregunta:** ¿Cómo se llama esta apertura y cuál es la idea?

> **Coach** (openai/gpt-oss-120b, 4.7 s): Se trata de la **Apertura Réti**, concretamente de la variante Anglo‑Slav con g3 (1.Nf3 d5 2.g3 Nf6 3.Bg2 c6)【1†source】.  
> 
> La idea es muy flexible: con el caballo en f3 y el alfil fianchetado en g2 controlas e4 y presionas el centro sin ocuparlo con peones. El negro ha puesto un peón en d5 y c6, preparando …Bf5 o …e6 y manteniendo una estructura similar a la del Slav. Tú puedes seguir con c4 para desafiar d5, o jugar d3 y e4 cuando el centro esté preparado, manteniendo al rey seguro y las piezas listas para un ataque en el flanco‑rey.

**4.** Tú: d4 — buena · Coach: g6  
**5.** Tú: b3 — buena · Coach: a5  
**6.** Tú: a4 — buena · Coach: Bg7  
**7.** Tú: O-O — buena · Coach: Bf5  
**8.** Tú: Bb2 — buena · Coach: Na6  
**9.** Tú: Nbd2 — buena · Coach: Qc7  
**10.** Tú: Nh4 — buena · Coach: Bc8  

**Pregunta:** ¿Voy ganando o perdiendo, y qué plan me recomiendas?

> **Coach** (openai/gpt-oss-120b, 1.8 s): Estás ligeramente mejor: la evaluación de Stockfish muestra +0.2 peones a tu favor, lo que se traduce en una posición igualada con una ligera ventaja estadística (≈52 % de ganar).  
> 
> **Plan recomendado**  
> 1. **Re‑ubicar el caballo** Nhf3 para reforzar el centro y cubrir g5 y e5.  
> 2. **Activar la torre del flanco‑dama** con Rc1 para presionar la columna c y preparar c4 (o c3 si prefieres consolidar).  
> 3. **Consolidar el centro** mediante c3 y e4 cuando el negro haya completado su desarrollo; así tu alfil g2 tendrá una diagonal potente y el rey ya está seguro tras O‑O.  
> 
> Mientras tanto, el alfil negro ha retrocedido a c8, por lo que su presión es mínima; aprovecha esa “inactividad” para ganar espacio y crear amenazas en el centro y en la columna c.

**11.** Tú: Rc1 — buena · Coach: Qd6  
**12.** Tú: e4 — buena · Coach: Nxe4  
**13.** Tú: c3 — imprecisión (mejor Bxe4) · Coach: f5  
**14.** Tú: Rc2 — buena · Coach: b5  
**15.** Tú: axb5 — buena · Coach: Nb8  
**16.** Tú: c4 — buena · Coach: Bb7  
**17.** Tú: Qc1 — buena · Coach: cxb5  
**18.** Tú: Nxe4 — imprecisión (mejor cxb5) · Coach: dxe4  
**19.** Tú: Rd1 — buena · Coach: Na6  
**20.** Tú: cxb5 — imprecisión (mejor Bf1) · Coach: Nb4  

**Pregunta:** ¿Qué amenaza el coach con su última jugada?

> **Coach** (openai/gpt-oss-120b, 1.7 s): El caballo que acabo de colocar en **b4** tiene dos ideas principales:
> 
> 1. **Atacar tu torre en c2**. Desde b4 el caballo controla la casilla c2, de modo que en el próximo movimiento puede capturarla (Nxc2) y ganar una pieza de mucho mayor valor que el propio caballo.
> 
> 2. **Presionar la columna c** y preparar una infiltración en d3 o a3. Si la torre se mueve, el caballo puede saltar a d3 (o a a2 en algunos casos) creando amenazas contra tu rey y tus peones centrales.
> 
> En resumen, la amenaza inmediata es **capturar tu torre en c2**; por eso es crucial defenderla o contrajugar antes de que el caballo lo haga.

**21.** Tú: Rc5 — buena · Coach: O-O  
**22.** Tú: Ba1 — error (mejor Bf1) · Coach: f4  
> **Coach** (openai/gpt-oss-120b, 1.5 s): Tu Ba1 fue un error porque, tras ella, la respuesta más fuerte del rival (f4‑e3) aumentó drásticamente la ventaja del rival de –0,7 a –2,5 peones. La idea correcta habría sido jugar Bf1, que mantiene la presión y evita que el rival active su peón con f4‑e3, limitando la pérdida de material. En resumen, Ba1 permite la secuencia f4‑e3 que empeora tu posición, mientras que Bf1 habría contenido esa amenaza.

**23.** Tú: Qc4+ — buena · Coach: Bd5  
**24.** Tú: Rxd5 — buena · Coach: Nxd5  
**25.** Tú: Bxe4 — buena · Coach: e6  
**26.** Tú: Qd3 — buena · Coach: Rac8  
**27.** Tú: Bb2 — imprecisión (mejor Nf3) · Coach: Qb4  
**28.** Tú: Rd2 — buena · Coach: Rfe8  
**29.** Tú: Bf3 — buena · Coach: fxg3  
**30.** Tú: hxg3 — buena · Coach: Re7  

**Pregunta:** ¿Cuál ha sido mi peor jugada hasta ahora y por qué?

> **Coach** (qwen3.5:9b-q4_K_M, 22.8 s): Tu peor jugada fue la **22. Ba1**. Fue un error grave que te costó una ventaja ligera y bajó tu probabilidad de ganar del 44% al 29%. La idea correcta habría sido jugar **Bf1**, manteniendo la presión y evitando que el rival activara su peón con f4-e3, lo cual empeoraría tu posición. En resumen, Ba1 permitió una secuencia que aumentó la ventaja del rival, mientras que Bf1 habría contenido esa amenaza.

**31.** Tú: Ng2 — buena · Coach: Rb8  
**32.** Tú: Bg4 — imprecisión (mejor Be2) · Coach: Qxb5  
**33.** Tú: Qf3 — error (mejor Qe4) · Coach: Qxb3  
> **Coach** (openai/gpt-oss-120b, 1.3 s): Al jugar **Qf3** la ventaja del rival se amplió de ‑2.6 a ‑4.2 peones, pues la respuesta más fuerte **Qxb3** (seguida de **Qe2** y **Kh8**) incrementó decisivamente su material. La idea correcta habría sido **Qe4**, que evita esa captura y mantiene la posición mucho más equilibrada.

**34.** Tú: Qe2 — buena · Coach: Ree8  
**35.** Tú: Kh2 — buena · Coach: a4  
**36.** Tú: Rc2 — buena · Coach: a3  
**37.** Tú: Ba1 — buena · Coach: Qb7  
**38.** Tú: Ne1 — buena · Coach: h5  
**39.** Tú: Bh3 — buena · Coach: Nf6  
**40.** Tú: Rc3 — buena · Coach: Qe4  
**41.** Tú: Qa2 — error (mejor Re3) · Coach: Qxe1  
> **Coach** (openai/gpt-oss-120b, 1.2 s): Tu Qa2 empeoró drásticamente la evaluación, pasando de ‑4.4 a ‑7.9 peones, porque dejó sin defensa el peón en d4 y el caballo en e1 y permitió que la respuesta más fuerte del rival (Qxe1‑Qd1) capturara la pieza sin defensa. La idea correcta habría sido jugar Re3, que protege esas debilidades y evita la captura decisiva. En resumen, Qa2 expuso piezas vulnerables y perdió material que Re3 habría salvado.

**42.** Tú: Rc1 — buena · Coach: Ng4+  
**43.** Tú: Bxg4 — buena · Coach: Qxc1  
**44.** Tú: Bf3 — buena · Coach: Qb1  
**45.** Tú: Qe2 — buena · Coach: Qxa1  
**46.** Tú: Be4 — buena · Coach: Qb2  
**47.** Tú: Bc2 — buena · Coach: a2  
**48.** Tú: Bd1 — buena · Coach: Qxe2  
**49.** Tú: g4 — buena · Coach: Bxd4  
**50.** Tú: Ba4 — buena · Coach: Qxf2+  
**51.** Tú: Kh3 — buena · Coach: hxg4+  
**52.** Tú: Kxg4 — buena · Coach: Qg2+  
**53.** Tú: Kf4 — buena · Coach: a1=Q  
**54.** Tú: Bb5 — buena · Coach: Qc1#  

## Resumen

- Resultado: 0-1 (checkmate)
- Jugadas del usuario: 54 (buena 46, imprecisión 5, error 3)
- Turnos con LLM: 7 · mediana 1.7 s · openai/gpt-oss-120b: 6, qwen3.5:9b-q4_K_M: 1
- Turnos sin LLM (jugada buena o imprecisión): 51

## PGN

```
[Event "ChessTrack AI · partida contra el coach"]
[Site "?"]
[Date "2026.11.21"]
[Round "?"]
[White "Tú"]
[Black "Coach (nivel 4)"]
[Result "0-1"]

1. Nf3 d5 2. g3 Nf6 3. Bg2 c6 4. d4 g6 5. b3 a5 6. a4 Bg7 7. O-O Bf5 8. Bb2 Na6 9. Nbd2 Qc7 10. Nh4 Bc8 11. Rc1 Qd6 12. e4 Nxe4 13. c3 f5 14. Rc2 b5 15. axb5 Nb8 16. c4 Bb7 17. Qc1 cxb5 18. Nxe4 dxe4 19. Rd1 Na6 20. cxb5 Nb4 21. Rc5 O-O 22. Ba1 f4 23. Qc4+ Bd5 24. Rxd5 Nxd5 25. Bxe4 e6 26. Qd3 Rac8 27. Bb2 Qb4 28. Rd2 Rfe8 29. Bf3 fxg3 30. hxg3 Re7 31. Ng2 Rb8 32. Bg4 Qxb5 33. Qf3 Qxb3 34. Qe2 Ree8 35. Kh2 a4 36. Rc2 a3 37. Ba1 Qb7 38. Ne1 h5 39. Bh3 Nf6 40. Rc3 Qe4 41. Qa2 Qxe1 42. Rc1 Ng4+ 43. Bxg4 Qxc1 44. Bf3 Qb1 45. Qe2 Qxa1 46. Be4 Qb2 47. Bc2 a2 48. Bd1 Qxe2 49. g4 Bxd4 50. Ba4 Qxf2+ 51. Kh3 hxg4+ 52. Kxg4 Qg2+ 53. Kf4 a1=Q 54. Bb5 Qc1# 0-1
```
