"""FastAPI entry point for the booking recommendation MVP."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from app.models.request import BookingRequest
from app.models.response import RecommendationResult
from app.models.approval import ApprovalDecision
from app.orchestrator.pipeline import run_pipeline
from app.mock.knowledge_base import get_vector_store
from app import approval_store

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the mock knowledge base on startup."""
    logger.info("Initializing mock knowledge base...")
    get_vector_store()
    logger.info("Knowledge base ready.")
    yield


app = FastAPI(
    title="AI Booking Recommendation MVP",
    description="Online workflow with mocked knowledge base",
    version="0.1.0",
    lifespan=lifespan,
)



@app.post("/recommend", response_model=RecommendationResult)
async def recommend(request: BookingRequest):
    """Run the full recommendation pipeline."""
    try:
        result = await run_pipeline(request)
        return result
    except Exception as e:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/approvals/pending", response_model=list[RecommendationResult])
async def list_pending():
    """List all recommendations waiting for human review."""
    return approval_store.list_pending()


@app.get("/approvals/{approval_id}", response_model=RecommendationResult)
async def get_approval(approval_id: str):
    """Get a specific pending recommendation by approval ID."""
    result = approval_store.get_pending(approval_id)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")
    return result


@app.post("/approvals/{approval_id}/approve", response_model=RecommendationResult)
async def approve_recommendation(approval_id: str, decision: ApprovalDecision):
    """Approve a recommendation that was held for human review."""
    result = approval_store.approve(approval_id, decision.reviewer, decision.comment)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")
    logger.info(f"Recommendation {approval_id} approved by {decision.reviewer}")
    return result


@app.post("/approvals/{approval_id}/reject", response_model=RecommendationResult)
async def reject_recommendation(approval_id: str, decision: ApprovalDecision):
    """Reject a recommendation that was held for human review."""
    result = approval_store.reject(approval_id, decision.reviewer, decision.comment)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")
    logger.info(f"Recommendation {approval_id} rejected by {decision.reviewer}")
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
