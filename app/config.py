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

    # Modelo de IA con formato "proveedor:modelo". Cambiarlo no requiere tocar código.
    ai_model: str = "google:gemini-3.5-flash-lite"
    # `str | None = None`: si no está en .env, vale None (los tests no la necesitan)
    google_api_key: str | None = None


# Una única instancia que importan los demás módulos: `from app.config import settings`
settings = Settings()
