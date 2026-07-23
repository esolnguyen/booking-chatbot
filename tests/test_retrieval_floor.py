"""Unit tests for the retrieval relevance floor (app/mock/knowledge_base.py).

Covers the pure ``_filter_by_relevance`` helper only, so no embeddings, vector
store, or network are needed — the heavy Chroma imports stay lazy.
"""

from langchain.schema import Document

from app.mock.knowledge_base import _filter_by_relevance


def _doc(doc_id: str) -> Document:
    return Document(page_content=doc_id, metadata={"id": doc_id})


def test_keeps_docs_at_or_above_threshold():
    scored = [(_doc("A"), 0.9), (_doc("B"), 0.6), (_doc("C"), 0.3)]
    kept = _filter_by_relevance(scored, 0.6)
    assert [d.metadata["id"] for d in kept] == ["A", "B"]


def test_boundary_score_is_inclusive():
    scored = [(_doc("A"), 0.5)]
    assert _filter_by_relevance(scored, 0.5) == [scored[0][0]]


def test_drops_everything_below_threshold():
    scored = [(_doc("A"), 0.2), (_doc("B"), 0.1)]
    assert _filter_by_relevance(scored, 0.5) == []


def test_zero_threshold_keeps_all():
    scored = [(_doc("A"), 0.9), (_doc("B"), 0.0)]
    kept = _filter_by_relevance(scored, 0.0)
    assert [d.metadata["id"] for d in kept] == ["A", "B"]


def test_empty_input_returns_empty():
    assert _filter_by_relevance([], 0.5) == []


def test_preserves_input_order():
    scored = [(_doc("C"), 0.95), (_doc("A"), 0.8), (_doc("B"), 0.7)]
    kept = _filter_by_relevance(scored, 0.6)
    assert [d.metadata["id"] for d in kept] == ["C", "A", "B"]
