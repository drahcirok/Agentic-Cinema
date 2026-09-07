from pydantic_settings import BaseSettings, SettingsConfigDict

# Backends disponibles:
#   "developer"  — usa GEMINI_API_KEY (modo local/desarrollo)
#   "vertex_ai"  — usa Application Default Credentials de Google Cloud (producción)
_VALID_BACKENDS = {"developer", "vertex_ai"}
_VALID_TICKET_STORAGE_BACKENDS = {"sqlite", "firestore"}


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

    # --- Google Cloud Storage ---
    # Nombre del bucket GCS donde se almacenan los videos de referencia.
    # No contiene credenciales; el acceso usa ADC automáticamente.
    # Requerido en producción (Cloud Run); opcional en desarrollo local.
    google_cloud_storage_bucket: str | None = None

    # --- Persistencia de tickets ---
    # SQLite se conserva para desarrollo local. Cloud Run debe usar Firestore,
    # porque el sistema de archivos de sus instancias es efímero.
    ticket_storage_backend: str = "sqlite"
    firestore_collection: str = "postproduction_tickets"
    user_profile_collection: str = "user_profiles"
    # ID de la base Native Mode creada para FrameFlow. Google reserva
    # "(default)" para la base predeterminada del proyecto.
    firestore_database_id: str = "(default)"

    # --- Autenticación de supervisores ---
    # Al activarse, todas las rutas de tickets exigen un Firebase ID token.
    # Firebase Admin usa ADC en Cloud Run, igual que Firestore y Vertex AI.
    auth_required: bool = False

    # Lista separada por comas. En producción contiene el dominio de Vercel.
    cors_allowed_origins: str = "http://localhost:3000"

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

    def validate_storage(self) -> None:
        """Lanza ValueError si la configuración de Cloud Storage está incompleta."""
        if not self.google_cloud_storage_bucket:
            raise ValueError(
                "GOOGLE_CLOUD_STORAGE_BUCKET es requerido para subir videos."
            )

    @property
    def is_firestore(self) -> bool:
        return self.ticket_storage_backend == "firestore"

    def validate_ticket_storage(self) -> None:
        """Valida la configuración de persistencia sin exponer credenciales."""
        if self.ticket_storage_backend not in _VALID_TICKET_STORAGE_BACKENDS:
            raise ValueError(
                f"TICKET_STORAGE_BACKEND='{self.ticket_storage_backend}' no es válido. "
                f"Valores permitidos: {sorted(_VALID_TICKET_STORAGE_BACKENDS)}."
            )
        if self.is_firestore and not self.google_cloud_project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT es requerido cuando TICKET_STORAGE_BACKEND=firestore."
            )
        if not self.firestore_collection.strip():
            raise ValueError("FIRESTORE_COLLECTION no puede estar vacío.")
        if not self.user_profile_collection.strip():
            raise ValueError("USER_PROFILE_COLLECTION no puede estar vacío.")
        if not self.firestore_database_id.strip():
            raise ValueError("FIRESTORE_DATABASE_ID no puede estar vacío.")

    def validate_auth(self) -> None:
        """Valida únicamente lo necesario cuando se protege la API con Firebase."""
        if self.auth_required and not self.google_cloud_project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT es requerido cuando AUTH_REQUIRED=true."
            )

    @property
    def cors_origins(self) -> list[str]:
        """Normaliza orígenes CORS evitando entradas vacías."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
