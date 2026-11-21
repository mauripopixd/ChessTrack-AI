"""Prueba de humo contra una API ya levantada (checkpoint de la Etapa 2).

Recorre el flujo completo por HTTP: health → registro → login → subir las 5 partidas
de muestra → re-subirlas (duplicadas) → listarlas → leer las jugadas de una.
Cada ejecución usa un usuario con nombre aleatorio. Sale con código 1 al primer fallo.

    docker compose up -d --build --wait
    python -m scripts.smoke_test                 # contra http://127.0.0.1:8000
    python -m scripts.smoke_test http://otro:8000
"""

import secrets
import sys
from pathlib import Path

import httpx

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"
COLORES = ["white", "black", "black", "white", "black"]  # weytey en cada muestra


def comprobar(condicion: bool, mensaje: str) -> None:
    print(("  ok   " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        raise SystemExit(1)


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    usuario = f"smoke_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(16)
    print(f"Smoke test contra {base} (usuario {usuario})")

    with httpx.Client(base_url=base, timeout=30) as c:
        r = c.get("/health")
        comprobar(r.status_code == 200 and r.json()["database"] == "ok", f"GET /health → {r.status_code}")

        r = c.post(
            "/auth/register",
            json={"email": f"{usuario}@example.com", "username": usuario, "password": password},
        )
        comprobar(r.status_code == 201, f"POST /auth/register → {r.status_code}")

        r = c.post("/auth/login", data={"username": usuario, "password": password})
        comprobar(r.status_code == 200, f"POST /auth/login → {r.status_code}")
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

        archivo = (SAMPLES / "varias.pgn").read_bytes()
        r = c.post("/games", files={"file": ("varias.pgn", archivo)}, data={"player": "weytey"})
        creadas = r.json().get("created", []) if r.status_code == 201 else []
        comprobar(
            [g["user_color"] for g in creadas] == COLORES,
            f"POST /games → {r.status_code}, {len(creadas)} partidas con sus colores",
        )

        r = c.post("/games", files={"file": ("varias.pgn", archivo)})
        comprobar(r.status_code == 200 and len(r.json()["duplicates"]) == 5, "re-subida → 5 duplicadas")

        r = c.get("/games", params={"limit": 2})
        comprobar(r.json()["total"] == 5 and len(r.json()["items"]) == 2, "GET /games paginado")

        primera = creadas[0]
        r = c.get(f"/games/{primera['id']}/moves")
        jugadas = r.json()
        comprobar(
            r.status_code == 200 and len(jugadas) == primera["move_count"] and jugadas[-1]["san"] == "Ra8#",
            f"GET /games/{{id}}/moves → {len(jugadas)} jugadas, termina en {jugadas[-1]['san']}",
        )

    print("Smoke test superado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
