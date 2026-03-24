"""In-memory store for pending approvals (swap for DB in production)."""

import uuid
from datetime import datetime
from app.models.response import RecommendationResult
from app.models.approval import ApprovalStatus, PendingApproval

# In-memory stores
_pending: dict[str, RecommendationResult] = {}
_approvals: dict[str, PendingApproval] = {}


def create_pending(result: RecommendationResult) -> str:
    """Store a result that needs human review. Returns approval_id."""
    approval_id = str(uuid.uuid4())
    result.approval_id = approval_id
    result.approval_status = ApprovalStatus.pending
    _pending[approval_id] = result
    _approvals[approval_id] = PendingApproval(approval_id=approval_id)
    return approval_id


def get_pending(approval_id: str) -> RecommendationResult | None:
    return _pending.get(approval_id)



def approve(approval_id: str, reviewer: str = "", comment: str = "") -> RecommendationResult | None:
    result = _pending.get(approval_id)
    if not result:
        return None
    result.approval_status = ApprovalStatus.approved
    approval = _approvals[approval_id]
    approval.status = ApprovalStatus.approved
    approval.reviewer = reviewer
    approval.review_comment = comment
    approval.reviewed_at = datetime.utcnow()
    return result


def reject(approval_id: str, reviewer: str = "", comment: str = "") -> RecommendationResult | None:
    result = _pending.get(approval_id)
    if not result:
        return None
    result.approval_status = ApprovalStatus.rejected
    approval = _approvals[approval_id]
    approval.status = ApprovalStatus.rejected
    approval.reviewer = reviewer
    approval.review_comment = comment
    approval.reviewed_at = datetime.utcnow()
    return result


def list_pending() -> list[RecommendationResult]:
    return [r for r in _pending.values() if r.approval_status == ApprovalStatus.pending]
