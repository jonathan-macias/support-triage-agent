"""Configuración de la aplicación.

`BaseSettings` (de pydantic-settings) lee cada atributo de las variables de
entorno o del archivo `.env`. Por ejemplo, `database_url` se rellena con la
variable `DATABASE_URL`. Así no escribimos contraseñas dentro del código.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Support Triage API"
    # pg8000 es un driver de PostgreSQL escrito 100% en Python (no necesita DLLs)
    database_url: str = "postgresql+pg8000://tickets:tickets@localhost:5433/tickets"


# Una única instancia que importan los demás módulos: `from app.config import settings`
settings = Settings()
