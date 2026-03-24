"""Models for human-in-the-loop approval workflow."""

from enum import Enum
from pydantic import BaseModel
from datetime import datetime


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApprovalDecision(BaseModel):
    reviewer: str = ""
    comment: str = ""


class PendingApproval(BaseModel):
    approval_id: str
    status: ApprovalStatus = ApprovalStatus.pending
    created_at: datetime = datetime.utcnow()
    reviewer: str = ""
    review_comment: str = ""
    reviewed_at: datetime | None = None
