from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings come from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # "local" saves files to a folder; "azure" saves to Azure Blob Storage
    storage_backend: str = "local"
    local_storage_dir: str = "./data/uploads"
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "documents"

    # SQLite for local work; later an Azure SQL connection URL
    database_url: str = "sqlite:///./docmind.db"

    max_upload_mb: int = 25


settings = Settings()
