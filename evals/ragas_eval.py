"""RAGAS evaluation of the RAG layer — LIVE only.

RAGAS scores the retrieval + generation quality the routing evals can't:
faithfulness (is the answer grounded in the retrieved context?), answer
relevancy, and context precision. These require an LLM + embedding *judge*, so
they only run against real Azure OpenAI — there is no offline RAGAS.

Design:
  - ``build_ragas_samples`` is PURE: it turns scenarios + pipeline outcomes into
    the {question, answer, contexts, ground_truth} records RAGAS consumes. Unit-
    tested without importing ragas (which is a heavy, optional dependency).
  - ``evaluate_rag`` imports ragas lazily, wraps the Azure LLM + embeddings as
    judges, and runs the metrics the data supports. Raises a clear error if ragas
    is not installed or Azure creds are missing.

Contexts are reconstructed by calling the real retriever, so the judged context
is exactly what the pipeline would retrieve for each request.
"""

from __future__ import annotations

from typing import Callable

from evals.harness import ScenarioOutcome, _build_request


def _render_question(req: dict) -> str:
    """A natural-language question mirroring the booking request."""
    tier = req.get("tier", "standard")
    purpose = req.get("trip_purpose", "business")
    return (
        f"Recommend a policy-compliant flight and hotel for a {tier}-tier "
        f"{purpose} trip from {req['origin']} to {req['destination']} "
        f"({req.get('departure_date')} to {req.get('return_date')})."
    )


def default_context_provider(req: dict) -> list[str]:
    """Reconstruct the retrieved context strings for a request (LIVE retrieval)."""
    from app.orchestrator.retriever import retrieve_context

    request = _build_request(req)
    context = retrieve_context(request)
    return [doc.page_content for docs in context.values() for doc in docs]


def build_ragas_samples(
    scenarios: list[dict],
    outcomes: list[ScenarioOutcome],
    context_provider: Callable[[dict], list[str]] = default_context_provider,
) -> list[dict]:
    """Build RAGAS records from scenarios + their pipeline outcomes (pure).

    Only scenarios that produced an answer (an explanation) are included — a
    human_review escalation with no recommendation text is not a RAG sample.
    ``ground_truth`` is filled from ``expected.reference_answer`` when present so
    reference-based metrics (context recall / answer correctness) can run.
    """
    by_id = {o.id: o for o in outcomes}
    samples: list[dict] = []
    for scenario in scenarios:
        outcome = by_id.get(scenario["id"])
        if outcome is None or outcome.result is None:
            continue
        answer = (outcome.result.explanation or "").strip()
        if not answer:
            continue
        req = scenario["request"]
        sample = {
            "question": _render_question(req),
            "answer": answer,
            "contexts": context_provider(req),
        }
        reference = scenario.get("expected", {}).get("reference_answer")
        if reference:
            sample["ground_truth"] = reference
        samples.append(sample)
    return samples


def _default_metrics(samples: list[dict]):
    """Pick metrics the data supports (ragas imported lazily by the caller)."""
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        faithfulness,
    )

    metrics = [faithfulness, answer_relevancy, context_precision]
    if any("ground_truth" in s for s in samples):
        from ragas.metrics import context_recall

        metrics.append(context_recall)
    return metrics


def evaluate_rag(
    scenarios: list[dict],
    outcomes: list[ScenarioOutcome],
    context_provider: Callable[[dict], list[str]] = default_context_provider,
) -> dict:
    """Run RAGAS over the live outcomes and return {metric_name: score}.

    LIVE only. Requires ``ragas`` installed and Azure creds configured; raises a
    RuntimeError with a clear message otherwise.
    """
    samples = build_ragas_samples(scenarios, outcomes, context_provider)
    if not samples:
        return {"samples": 0}

    try:
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
    except ImportError as exc:  # pragma: no cover - optional heavy dep
        raise RuntimeError(
            "RAGAS eval needs `pip install ragas datasets`. Live-only; not "
            "installed by default because it pulls heavy dependencies."
        ) from exc

    from app.config import settings

    if not (settings.azure_openai_api_key and settings.azure_openai_chat_deployment):
        raise RuntimeError("RAGAS eval needs Azure OpenAI credentials (see --live).")

    from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

    judge_llm = LangchainLLMWrapper(
        AzureChatOpenAI(
            azure_deployment=settings.azure_openai_chat_deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            temperature=0.0,
        )
    )
    judge_emb = LangchainEmbeddingsWrapper(
        AzureOpenAIEmbeddings(
            azure_deployment=settings.azure_openai_embedding_deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
    )

    dataset = Dataset.from_list(samples)
    result = ragas_evaluate(
        dataset,
        metrics=_default_metrics(samples),
        llm=judge_llm,
        embeddings=judge_emb,
    )
    scores = {k: float(v) for k, v in result.items() if isinstance(v, (int, float))}
    scores["samples"] = len(samples)
    return scores
