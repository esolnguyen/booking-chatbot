"""Knowledge base using local ChromaDB for vector similarity search."""

from __future__ import annotations

from datetime import datetime

import chromadb
from langchain_community.vectorstores import Chroma
from langchain_openai import AzureOpenAIEmbeddings
from langchain.schema import Document

from app.config import settings
from app.mock.seed_data import TRAVEL_POLICIES, DESTINATION_GUIDES, EVENT_DATA

CURRENT_YEAR = datetime.now().year
FRESHNESS_MAX_AGE = CURRENT_YEAR - 2020  # 6-year window

_vector_store: Chroma | None = None
_chroma_client: chromadb.ClientAPI | None = None


def _build_documents() -> list[Document]:
    docs = []
    for p in TRAVEL_POLICIES:
        docs.append(Document(
            page_content=p["content"],
            metadata={
                "id": p["id"],
                "title": p["title"],
                "source_type": "policy",
                "policy_type": p["policy_type"],
                "tier": p["tier"],
                "region": p["region"],
                "year": p["year"],
            },
        ))
    for d in DESTINATION_GUIDES:
        docs.append(Document(
            page_content=d["content"],
            metadata={
                "id": d["id"],
                "source_type": "destination",
                "city": d["city"],
                "country": d["country"],
                "risk_level": d["risk_level"],
                "year": d["year"],
            },
        ))
    for e in EVENT_DATA:
        docs.append(Document(
            page_content=e["content"],
            metadata={
                "id": e["id"],
                "source_type": "event",
                "city": e["city"],
                "event": e["event"],
                "dates": e["dates"],
                "impact": e["impact"],
                "year": e["year"],
            },
        ))
    return docs


def _build_embeddings() -> AzureOpenAIEmbeddings:
    return AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def get_vector_store() -> Chroma:
    """Get or create the Chroma vector store (singleton, ephemeral)."""
    global _vector_store, _chroma_client
    if _vector_store is None:
        _chroma_client = chromadb.EphemeralClient()
        embeddings = _build_embeddings()
        docs = _build_documents()
        _vector_store = Chroma.from_documents(
            docs,
            embeddings,
            client=_chroma_client,
            collection_name="knowledge_base",
        )
    return _vector_store


def search_knowledge_base(
    query: str,
    top_k: int = 5,
    filter_metadata: dict | None = None,
) -> list[Document]:
    """Search the knowledge base with optional metadata filtering."""
    store = get_vector_store()

    where_filter = None
    if filter_metadata:
        conditions = [
            {k: {"$eq": v}} for k, v in filter_metadata.items() if v is not None
        ]
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif conditions:
            where_filter = {"$and": conditions}

    results = store.similarity_search(query, k=top_k, filter=where_filter)
    return results


def compute_evidence_freshness(docs: list[Document]) -> float:
    """Compute a 0-1 freshness score from document year metadata.

    Newer documents (closer to CURRENT_YEAR) score higher.
    Returns average freshness across all docs, or 0.5 if no docs.
    """
    if not docs:
        return 0.5
    scores = []
    for doc in docs:
        year = doc.metadata.get("year")
        if year is None:
            scores.append(0.5)
            continue
        age = CURRENT_YEAR - int(year)
        score = max(0.0, 1.0 - age / FRESHNESS_MAX_AGE)
        scores.append(score)
    return sum(scores) / len(scores)
