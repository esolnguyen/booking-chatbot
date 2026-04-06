from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure OpenAI (cognitiveservices) settings
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""  # https://xxx.cognitiveservices.azure.com/
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_chat_deployment: str = ""  # e.g. "gpt-4o-mini"
    # Set to true for o-series / gpt-5+ models that don't accept temperature
    azure_openai_disable_temperature: bool = False

    # LLM provider -- "azure" or "google"
    llm_provider: str = "azure"

    # Google Gemini (google-genai SDK)
    google_ai_api_key: str = ""
    google_ai_model: str = "gemini-2.0-flash"

    # Verification confidence threshold
    verification_confidence_threshold: float = 0.60

    # Set to false to skip the LLM verification call (uses deterministic checks only)
    verification_llm_enabled: bool = True

    # Set to true to use rule-based intent parsing (instant, no LLM call).
    # Falls back to LLM automatically when the rules can't confidently parse the input.
    intent_rule_based: bool = False

    # Crawler -- route pairs as "ORIGIN-DESTINATION", e.g. "SGN-SYD"
    # In .env: CRAWL_ROUTES=SGN-SYD,SYD-SGN,SGN-NRT
    crawl_routes: str = "SGN-SYD,SYD-SGN,SGN-MEL,MEL-SGN,SGN-BNE,BNE-SGN,SGN-NRT,NRT-SGN,SGN-HAN,HAN-SGN"
    crawl_interval_minutes: int = 5
    crawl_stay_duration_days: int = 4  # nights per trip when building booking URLs

    @property
    def crawl_route_list(self) -> list[str]:
        """Parse crawl_routes string into a list."""
        return [r.strip() for r in self.crawl_routes.split(",") if r.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
