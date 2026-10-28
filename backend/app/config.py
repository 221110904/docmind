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

    # OCR: "none" leaves scans and images waiting; "azure" uses Document Intelligence
    ocr_backend: str = "none"
    document_intelligence_endpoint: str = ""
    document_intelligence_key: str = ""
    # The free (F0) tier reads only 2 pages per request and accepts 4 MB at most,
    # so scanned PDFs are sent in small batches. Raise both limits on a paid tier.
    ocr_pages_per_request: int = 2
    ocr_max_request_mb: int = 4

    # Chunking (about 4 characters per token, so 900 characters is roughly 225 tokens)
    chunk_chars: int = 900
    chunk_overlap_chars: int = 100

    # Embeddings: "fake" is a local stand-in (not semantic); "azure" uses Azure OpenAI.
    # 1024 numbers per vector keeps the free search tier (50 MB) roomy; the model
    # supports 3072. Changing this later means re-creating the index and re-embedding.
    embedding_backend: str = "fake"
    embedding_dimensions: int = 1024
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    # Search index: "memory" is a local stand-in; "azure" uses Azure AI Search
    search_backend: str = "memory"
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "docmind-chunks"

    # Q&A: "fake" is a local stand-in; "azure" asks the GPT-4o deployment
    qa_backend: str = "fake"
    azure_openai_chat_deployment: str = "gpt-4o"
    qa_max_context_chars: int = 12000

    # Websites allowed to call the API from a browser (comma-separated)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


settings = Settings()
