from pydantic import BaseModel
from app.models.option import BookingOption
from app.models.approval import ApprovalStatus


class RecommendationResult(BaseModel):
    route: str  # auto_suggest, suggest_with_caution, human_review
    confidence: float
    options: list[BookingOption] = []
    explanation: str = ""
    evidence_refs: list[str] = []
    risk_flags: list[str] = []
    verification_notes: str = ""
    # Human-in-the-loop fields
    approval_required: bool = False
    approval_id: str | None = None
    approval_status: ApprovalStatus | None = None
