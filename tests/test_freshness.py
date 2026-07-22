"""Unit tests for evidence freshness scoring.

``compute_evidence_freshness`` is pure (no vector store), so these run without
chromadb installed — the heavy imports in knowledge_base are loaded lazily.
"""

from langchain.schema import Document
from app.mock.knowledge_base import (
    compute_evidence_freshness,
    CURRENT_YEAR,
)


def _doc(year):
    return Document(page_content="x", metadata={"year": year})


def test_no_docs_returns_neutral():
    assert compute_evidence_freshness([]) == 0.5


def test_current_year_scores_max():
    assert compute_evidence_freshness([_doc(CURRENT_YEAR)]) == 1.0


def test_missing_year_scores_neutral():
    assert compute_evidence_freshness([Document(page_content="x", metadata={})]) == 0.5


def test_older_doc_scores_lower_than_newer():
    newer = compute_evidence_freshness([_doc(CURRENT_YEAR - 1)])
    older = compute_evidence_freshness([_doc(CURRENT_YEAR - 5)])
    assert newer > older


def test_average_across_docs():
    score = compute_evidence_freshness([_doc(CURRENT_YEAR), _doc(CURRENT_YEAR)])
    assert score == 1.0
