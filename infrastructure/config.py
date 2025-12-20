from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LLM Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    
    # Chat/Reasoning Model (for SQL generation, API reasoning, RAG answering)
    # Development: llama3.2:3b (fast, ~2GB)
    # Production: llama3.1:8b-instruct (accurate, ~5GB)
    LLM_MODEL: str = "llama3.2:3b"
    
    # Embedding Model (for intent routing, document retrieval, semantic search)
    # Recommended: nomic-embed-text (fast, ~274MB, good quality)
    EMBEDDING_MODEL: str = "nomic-embed-text"
    
    # Database
    # Using 'localhost' by default for local development. 
    # Docker compose might override this via .env or env vars (e.g. host.docker.internal)
    DB_URI: str = "postgresql+psycopg2://entity:password@localhost:5434/entdb"
    
    # Vector Store
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "rag_collection"
    
    # App
    API_TITLE: str = "Sarvantaryamin Agent"
    API_VERSION: str = "v1"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
