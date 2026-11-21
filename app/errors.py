"""Errores de dominio: lo que puede salir mal en la lógica de negocio.

Los services lanzan estos errores y los routers los traducen a HTTP (409, 401…).
Así los services no saben nada de HTTP y se pueden usar igual desde un script
(scripts/import_raw.py) o, más adelante, desde el agente de la Etapa 5.
"""


class DuplicateUserError(Exception):
    """Ya existe un usuario con ese email o username."""

    def __init__(self, field: str) -> None:
        super().__init__(f"Ya existe un usuario con ese {field}")
        self.field = field


class InvalidCredentialsError(Exception):
    """Usuario inexistente o contraseña incorrecta (a propósito, no se distingue cuál)."""


class ConcurrentImportError(Exception):
    """Otra petición guardó la misma partida a la vez; la BD lo impidió."""
