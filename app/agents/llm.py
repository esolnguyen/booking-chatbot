"""Unified LLM client — Azure OpenAI or Google Gemini.

Usage:
    from app.agents.llm import sync_chat, async_chat

    # Sync (response_verifier, chatbot main loop)
    text = sync_chat(messages, temperature=0.0)

    # Async (recommendation agent, verification agent)
    text = await async_chat(messages, temperature=0.1)

messages format (same as OpenAI):
    [
        {"role": "system",    "content": "..."},
        {"role": "user",      "content": "..."},
        {"role": "assistant", "content": "..."},
        ...
    ]

Provider is read from settings.llm_provider ("azure" or "google").
Pass provider= explicitly to override per-call.
"""

import logging
import time
from typing import Optional

from openai import AsyncAzureOpenAI, AzureOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0  # seconds

# ── Singletons ────────────────────────────────────────────────────
_azure_sync_client:  AzureOpenAI | None = None
_azure_async_client: AsyncAzureOpenAI | None = None
_google_client_instance = None


def _get_azure_sync() -> AzureOpenAI:
    global _azure_sync_client
    if _azure_sync_client is None:
        _azure_sync_client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
    return _azure_sync_client


def _get_azure_async() -> AsyncAzureOpenAI:
    global _azure_async_client
    if _azure_async_client is None:
        _azure_async_client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
    return _azure_async_client


def _get_google_client():
    global _google_client_instance
    if _google_client_instance is None:
        from google import genai
        from google.genai import types as _types
        _google_client_instance = genai.Client(
            api_key=settings.google_ai_api_key,
            http_options=_types.HttpOptions(
                # Limit to 2 attempts (1 retry). Default is 5 — with a 60s timeout
                # that means up to 4 × 60s = 240s worst case before failing.
                retry_options=_types.HttpRetryOptions(attempts=2),
            ),
        )
    return _google_client_instance


# ── Message helpers ───────────────────────────────────────────────

def _split_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract the system prompt and return the remaining history."""
    system = ""
    history = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            history.append(m)
    return system, history


def _to_gemini_contents(history: list[dict]):
    """Convert OpenAI-style message list to Gemini Content objects."""
    from google.genai import types
    contents = []
    for m in history:
        role = "user" if m["role"] == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=m["content"])])
        )
    return contents


def _log_input(label: str, messages: list[dict]) -> None:
    total_chars = sum(len(m.get("content", "")) for m in messages)
    logger.debug("[LLM] %-12s | ── INPUT (%d messages, %d chars) ──────────",
                 label, len(messages), total_chars)
    for i, m in enumerate(messages):
        logger.debug("[LLM] %-12s | msg[%d] role=%s:\n%s",
                     label, i, m["role"], m.get("content", ""))
    logger.debug(
        "[LLM] %-12s | ── END INPUT ───────────────────────────────", label)


def _log_output(label: str, content: str) -> None:
    logger.debug(
        "[LLM] %-12s | ── OUTPUT ──────────────────────────────────\n%s", label, content)


def _log_call(label: str, provider: str, elapsed: float, prompt_tokens: int, completion_tokens: int) -> None:
    logger.info(
        "[LLM] %-12s | %-6s | %.2fs | prompt=%d completion=%d total=%d",
        label, provider, elapsed, prompt_tokens, completion_tokens, prompt_tokens +
        completion_tokens,
    )


# ── Public API ────────────────────────────────────────────────────

def sync_chat(
    messages: list[dict],
    temperature: float = 0.0,
    provider: Optional[str] = None,
    max_tokens: Optional[int] = None,
    thinking_budget: Optional[int] = None,
    response_schema=None,
    timeout_ms: Optional[int] = None,
    label: str = "chat",
) -> str:
    """Synchronous chat completion."""
    p = provider or settings.llm_provider
    try:
        if p == "google":
            return _google_sync(messages, temperature, max_tokens, thinking_budget, response_schema, timeout_ms, label)
        return _azure_sync_chat(messages, temperature, max_tokens, label)
    except Exception as exc:
        logger.error("[LLM] %-12s | %s error: %s", label, p, exc)
        raise


async def async_chat(
    messages: list[dict],
    temperature: float = 0.1,
    provider: Optional[str] = None,
    max_tokens: Optional[int] = None,
    thinking_budget: Optional[int] = None,
    timeout_ms: Optional[int] = None,
    label: str = "chat",
) -> str:
    """Asynchronous chat completion."""
    p = provider or settings.llm_provider
    try:
        if p == "google":
            return await _google_async(messages, temperature, max_tokens, thinking_budget, timeout_ms, label)
        return await _azure_async_chat(messages, temperature, max_tokens, label)
    except Exception as exc:
        logger.error("[LLM] %-12s | %s error: %s", label, p, exc)
        raise


# ── Azure implementations ─────────────────────────────────────────

def _azure_sync_chat(messages: list[dict], temperature: float, max_tokens: Optional[int] = None, label: str = "chat") -> str:
    t0 = time.perf_counter()
    params: dict = {"timeout": _TIMEOUT, "top_p": 1, "seed": 42}
    if not settings.azure_openai_disable_temperature:
        params["temperature"] = temperature
    if max_tokens:
        params["max_completion_tokens"] = max_tokens
    response = _get_azure_sync().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        **params,
    )
    elapsed = time.perf_counter() - t0
    usage = response.usage
    _log_call(label, "azure", elapsed,
              usage.prompt_tokens, usage.completion_tokens)
    content = response.choices[0].message.content
    if content is None:
        raise ValueError(
            "Azure returned empty content (possible content filter)")
    _log_output(label, content)
    return content


async def _azure_async_chat(messages: list[dict], temperature: float, max_tokens: Optional[int] = None, label: str = "chat") -> str:
    t0 = time.perf_counter()
    params: dict = {"timeout": _TIMEOUT, "top_p": 1, "seed": 42}
    if not settings.azure_openai_disable_temperature:
        params["temperature"] = temperature
    if max_tokens:
        params["max_completion_tokens"] = max_tokens
    response = await _get_azure_async().chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        **params,
    )
    elapsed = time.perf_counter() - t0
    usage = response.usage
    _log_call(label, "azure", elapsed,
              usage.prompt_tokens, usage.completion_tokens)
    content = response.choices[0].message.content
    if content is None:
        raise ValueError(
            "Azure returned empty content (possible content filter)")
    _log_output(label, content)
    return content


# ── Google Gemini implementations ─────────────────────────────────

def _google_sync(messages: list[dict], temperature: float, max_tokens: Optional[int] = None, thinking_budget: Optional[int] = None, response_schema=None, timeout_ms: Optional[int] = None, label: str = "chat") -> str:
    from google.genai import types
    _log_input(label, messages)
    client = _get_google_client()
    system, history = _split_messages(messages)
    contents = _to_gemini_contents(history)

    cfg: dict = {
        "temperature": temperature,
        "top_p": 1,
        "top_k": 1,
        "seed": 42,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        "http_options": types.HttpOptions(timeout=timeout_ms or int(_TIMEOUT * 1000)),
    }
    if system:
        cfg["system_instruction"] = system
    if max_tokens:
        cfg["max_output_tokens"] = max_tokens
    if thinking_budget is not None:
        cfg["thinking_config"] = types.ThinkingConfig(
            thinking_budget=thinking_budget)

        cfg["thinking_config"] = types.ThinkingConfig(
            thinking_budget=thinking_budget)
    if response_schema is not None and thinking_budget > 0:
        cfg["response_mime_type"] = "application/json"
        cfg["response_schema"] = response_schema

    t0 = time.perf_counter()
    response = client.models.generate_content(
        model=settings.google_ai_model,
        contents=contents,
        config=types.GenerateContentConfig(**cfg),
    )
    elapsed = time.perf_counter() - t0
    meta = response.usage_metadata
    _log_call(label, "google", elapsed, meta.prompt_token_count or 0,
              meta.candidates_token_count or 0)
    _log_output(label, response.text)
    return response.text


async def _google_async(messages: list[dict], temperature: float, max_tokens: Optional[int] = None, thinking_budget: Optional[int] = None, timeout_ms: Optional[int] = None, label: str = "chat") -> str:
    from google.genai import types
    _log_input(label, messages)
    client = _get_google_client()
    system, history = _split_messages(messages)
    contents = _to_gemini_contents(history)

    cfg: dict = {
        "temperature": temperature,
        "top_p": 1,
        "top_k": 1,
        "seed": 42,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        "http_options": types.HttpOptions(timeout=timeout_ms or int(_TIMEOUT * 1000)),
    }
    if system:
        cfg["system_instruction"] = system
    if max_tokens:
        cfg["max_output_tokens"] = max_tokens
    if thinking_budget is not None:
        cfg["thinking_config"] = types.ThinkingConfig(
            thinking_budget=thinking_budget)

    t0 = time.perf_counter()
    response = await client.aio.models.generate_content(
        model=settings.google_ai_model,
        contents=contents,
        config=types.GenerateContentConfig(**cfg),
    )
    elapsed = time.perf_counter() - t0
    meta = response.usage_metadata
    _log_call(label, "google", elapsed, meta.prompt_token_count or 0,
              meta.candidates_token_count or 0)
    _log_output(label, response.text)
    return response.text
