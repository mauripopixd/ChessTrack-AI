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


class CoachRateLimitError(Exception):
    """El usuario agotó sus respuestas del LLM de la última hora (el límite gratuito es compartido)."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"Has usado tus {limit} respuestas del coach de la última hora: prueba más tarde")
        self.limit = limit


class CoachLLMUnavailableError(Exception):
    """Ningún LLM respondió (Groq sin cupo y Ollama apagado, por ejemplo)."""
