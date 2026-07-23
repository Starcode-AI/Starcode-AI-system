from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import current_user
from ..models import Conversation, Feedback, Message, User
from ..schemas import ApiMessage, FeedbackIn
from ..security import audit


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=ApiMessage)
def submit(payload: FeedbackIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    message = db.get(Message, payload.message_id)
    conversation = db.get(Conversation, message.conversation_id) if message else None
    if not message or not conversation or conversation.user_id != user.id or message.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    existing = db.scalar(
        select(Feedback).where(Feedback.user_id == user.id, Feedback.message_id == message.id)
    )
    if existing:
        existing.rating = payload.rating
        existing.category = payload.category
        existing.comment = payload.comment
        existing.reviewed = False
    else:
        db.add(Feedback(user_id=user.id, message_id=message.id, **payload.model_dump(exclude={"message_id"})))
    db.commit()
    audit(db, request, "feedback_submitted", user.id, "message", message.id, {"rating": payload.rating})
    return ApiMessage(message="Feedback saved for review")
