from pydantic_settings import BaseSettings, SettingsConfigDict

# Backends disponibles:
#   "developer"  — usa GEMINI_API_KEY (modo local/desarrollo)
#   "vertex_ai"  — usa Application Default Credentials de Google Cloud (producción)
_VALID_BACKENDS = {"developer", "vertex_ai"}


class Settings(BaseSettings):
    # --- Modo developer (opcional, solo desarrollo local) ---
    gemini_api_key: str | None = None

    # --- Modelo y backend ---
    gemini_model: str = "gemini-2.5-flash"
    gemini_backend: str = "developer"

    # --- Google Cloud / Vertex AI ---
    # Requerido cuando gemini_backend = "vertex_ai"
    google_cloud_project: str | None = None
    # "global" es requerido para el endpoint global de Vertex AI Gen AI
    google_cloud_location: str = "global"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def is_vertex_ai(self) -> bool:
        return self.gemini_backend == "vertex_ai"

    def validate_vertex_ai(self) -> None:
        """Lanza ValueError si la configuración de Vertex AI está incompleta."""
        if self.gemini_backend not in _VALID_BACKENDS:
            raise ValueError(
                f"GEMINI_BACKEND='{self.gemini_backend}' no es válido. "
                f"Valores permitidos: {sorted(_VALID_BACKENDS)}."
            )
        if self.is_vertex_ai and not self.google_cloud_project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT es requerido cuando GEMINI_BACKEND=vertex_ai."
            )


settings = Settings()
