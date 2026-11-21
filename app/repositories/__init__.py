"""Capa de acceso a datos: el único sitio del código que habla SQL.

Cada repositorio tiene dos partes:
- un `Protocol` (la interfaz): lo que los services pueden pedir;
- una implementación con SQLAlchemy (`Sql…Repository`).

Los services dependen del Protocol, no de SQLAlchemy (inversión de dependencias):
en los tests unitarios se les pasa un repositorio en memoria (tests/fakes.py).
"""
