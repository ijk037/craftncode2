"""
Chat Schemas — Sahayak AI
"""

from pydantic import BaseModel, Field

from app.models.enums import LanguageEnum
from app.schemas.chat_history import ChatHistoryRead
from app.schemas.common import SuccessResponse


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="User's question, in any of the 13 supported languages",
    )


class TranscribeResult(BaseModel):
    text: str = Field(description="Transcribed speech, in its original language/script")
    detected_language: str = Field(description="Best-effort language code detected by the STT model")


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: LanguageEnum


ChatAskResponse = SuccessResponse[ChatHistoryRead]
ChatHistoryListResponse = SuccessResponse[list[ChatHistoryRead]]
TranscribeResponse = SuccessResponse[TranscribeResult]
