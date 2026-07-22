"""Simple relevance reranker for retrieved documents."""

from langchain.schema import Document


def rerank_documents(
    documents: list[Document],
    query_keywords: list[str],
    top_k: int = 3,
) -> list[Document]:
    """Rerank documents by keyword overlap score. Simple but deterministic."""
    scored = []
    for doc in documents:
        content_lower = doc.page_content.lower()
        meta_text = " ".join(str(v) for v in doc.metadata.values()).lower()
        combined = content_lower + " " + meta_text

        score = sum(
            1 for kw in query_keywords if kw.lower() in combined
        )
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]
