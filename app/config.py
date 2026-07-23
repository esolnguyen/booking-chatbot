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

    # Agent loop: max recommendation attempts (1 initial + retries). The loop
    # only re-asks on *recoverable* failures (e.g. fabricated citations); it
    # never retries deterministic hard fails like sold-out inventory. Guardrail.
    max_agent_iterations: int = 2

    # Retrieval
    retrieval_top_k: int = 5
    rerank_top_k: int = 3
    # Minimum relevance score (0-1) a retrieved doc must clear to enter context.
    # 0.0 disables the floor (pure top-k). Raising it drops weak matches so they
    # don't pollute the prompt ("context rot"). Only applied when > 0.
    retrieval_min_score: float = 0.0

    # Telemetry (local-first — no third-party SaaS by default)
    telemetry_enabled: bool = True
    telemetry_console: bool = False  # print a per-run span summary to stdout
    telemetry_otel: bool = False  # export spans via OpenTelemetry if SDK present
    # Per-1k-token USD prices for cost estimation (defaults ~ gpt-4o-mini).
    chat_input_cost_per_1k: float = 0.00015
    chat_output_cost_per_1k: float = 0.0006

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
