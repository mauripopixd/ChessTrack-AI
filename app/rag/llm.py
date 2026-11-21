"""Cliente de LLM gratuito con respaldo: Groq (nube) → Ollama (local).

Los dos hablan el formato de "chat completions" de OpenAI, así que basta un cliente HTTP
y cambiar URL, modelo y clave. Orden:

1. **Groq** (`openai/gpt-oss-120b`): gratis con límites, sin tarjeta, rápido. Solo si hay
   GROQ_API_KEY en el entorno.
2. **Ollama** (modelo local, p. ej. Qwen 3.5 9B): gratis y sin límites, pero menos capaz.
   Se usa si no hay clave de Groq o si Groq falla (límite agotado, caída, red).

Por qué no Claude/ChatGPT con la suscripción del usuario: los planes de consumo (Claude
Pro/Max, ChatGPT Plus) no incluyen API, y Anthropic prohíbe usarlos como backend de apps.
"""

from dataclasses import dataclass

import httpx


class LLMUnavailableError(Exception):
    """Ningún proveedor respondió."""


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    api_key: str | None = None
    # Parámetros extra de cada proveedor. gpt-oss y Qwen 3.5 "piensan" antes de responder:
    # en Groq se limita el razonamiento; en Ollama se desactiva, porque con un modelo local
    # pequeño se come los tokens y la respuesta llega vacía o tarda 30 s.
    extra: dict | None = None


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str
    latency_ms: int
    tokens: int | None


def groq(api_key: str, model: str = "openai/gpt-oss-120b") -> Provider:
    return Provider("groq", "https://api.groq.com/openai/v1", model, api_key, {"reasoning_effort": "low"})


def ollama(model: str, base_url: str = "http://127.0.0.1:11434/v1") -> Provider:
    return Provider("ollama", base_url, model, None, {"reasoning_effort": "none"})


class LLMClient:
    def __init__(self, providers: list[Provider], timeout: float = 120.0) -> None:
        if not providers:
            raise ValueError("Hace falta al menos un proveedor")
        self.providers = providers
        self.timeout = timeout

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        """Prueba los proveedores en orden y devuelve la primera respuesta no vacía."""
        errores = []
        for p in self.providers:
            try:
                return self._llamar(p, system, user, max_tokens)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                # 429 (límite), 5xx, red caída, Ollama apagado o respuesta vacía: al siguiente.
                if isinstance(e, httpx.HTTPStatusError):
                    motivo = f"HTTP {e.response.status_code}"  # el mensaje de httpx es largo y multilínea
                else:
                    motivo = f"{type(e).__name__}: {e}"
                errores.append(f"{p.name}: {motivo}")
        raise LLMUnavailableError("; ".join(errores))

    def _llamar(self, p: Provider, system: str, user: str, max_tokens: int) -> Completion:
        cuerpo = {
            "model": p.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": 0.2,  # respuestas fieles a las fuentes, poco creativas
            **(p.extra or {}),
        }
        cabeceras = {"Authorization": f"Bearer {p.api_key}"} if p.api_key else {}
        r = httpx.post(f"{p.base_url}/chat/completions", json=cuerpo, headers=cabeceras, timeout=self.timeout)
        r.raise_for_status()
        datos = r.json()
        texto = (datos["choices"][0]["message"].get("content") or "").strip()
        if not texto:
            raise ValueError("respuesta vacía")
        return Completion(
            text=texto,
            provider=p.name,
            model=p.model,
            latency_ms=int(r.elapsed.total_seconds() * 1000),
            tokens=(datos.get("usage") or {}).get("total_tokens"),
        )
