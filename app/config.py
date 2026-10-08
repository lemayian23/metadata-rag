from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    readonly_database_url: str
    ollama_base_url: str = "http://host.docker.internal:11434"

    embedding_model: str = "nomic-embed-text"
    chat_model: str = "qwen2.5:1.5b"
    vision_model: str = "moondream"
    embedding_dim: int = 768

    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidates: int = 50
    rerank_top_k: int = 5

    chunk_size: int = 800
    chunk_overlap: int = 150
    default_top_k: int = 5
    max_context_tokens: int = 6000

    contextual_chunking: bool = True
    sql_max_rows: int = 100

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "ragpassword"
    graph_enabled: bool = True

    corrective_threshold: float = 0.0
    search_mode: str = "hybrid"
    multimodal_enabled: bool = True


settings = Settings()