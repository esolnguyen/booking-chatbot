from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure OpenAI (cognitiveservices) settings
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""  # https://xxx.cognitiveservices.azure.com/
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_chat_deployment: str = ""  # e.g. "gpt-4o-mini"
    azure_openai_embedding_deployment: str = ""  # e.g. "text-embedding-3-large"

    # Pipeline timeout budgets (seconds)
    retrieval_timeout: float = 5.0
    agent_timeout: float = 10.0
    verification_timeout: float = 10.0

    # Confidence routing thresholds
    auto_suggest_threshold: float = 0.85
    human_review_threshold: float = 0.60

    # Retrieval
    retrieval_top_k: int = 5
    rerank_top_k: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
