"""
Chat Endpoints — Sahayak AI
==============================
POST /api/v1/chat/ask          — ask the RAG assistant a question; answered
                                  in whichever of the 13 supported languages
                                  it was asked in
GET  /api/v1/chat/history      — list the current user's past conversation
                                  turns
POST /api/v1/chat/transcribe   — speech-to-text: upload an audio recording,
                                  get back the transcribed text
POST /api/v1/chat/speak        — text-to-speech: get back MP3 audio for a
                                  piece of text in a given language

Speech input/output are both opt-in — text-only clients can ignore
/transcribe and /speak entirely and just use /ask and /history as before.
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.core.config import settings
from app.core.exceptions import ValidationException
from app.database.database import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatAskResponse,
    ChatHistoryListResponse,
    ChatRequest,
    SpeakRequest,
    TranscribeResponse,
    TranscribeResult,
)
from app.schemas.chat_history import ChatHistoryRead
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])


def _svc(db: AsyncSession = Depends(get_db)) -> ChatService:
    return ChatService(db)


@router.post(
    "/ask",
    response_model=ChatAskResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask the multilingual scheme assistant a question",
)
async def ask(
    payload: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    svc: ChatService = Depends(_svc),
) -> ChatAskResponse:
    chat = await svc.ask(current_user.id, payload.message)
    return ChatAskResponse(data=ChatHistoryRead.model_validate(chat))


@router.get(
    "/history",
    response_model=ChatHistoryListResponse,
    summary="Get the current user's chat history, newest first",
)
async def history(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    svc: ChatService = Depends(_svc),
) -> ChatHistoryListResponse:
    chats = await svc.get_history(current_user.id, skip=skip, limit=limit)
    return ChatHistoryListResponse(data=[ChatHistoryRead.model_validate(c) for c in chats])


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Transcribe a spoken question to text (speech-to-text)",
)
async def transcribe(
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    svc: ChatService = Depends(_svc),
) -> TranscribeResponse:
    audio_bytes = await audio.read()
    max_bytes = settings.CHAT_MAX_AUDIO_UPLOAD_MB * 1024 * 1024
    if len(audio_bytes) > max_bytes:
        raise ValidationException(
            f"Audio file too large. Please keep recordings under {settings.CHAT_MAX_AUDIO_UPLOAD_MB}MB."
        )
    text, detected_language = svc.transcribe(audio_bytes, audio.filename or "recording.webm")
    return TranscribeResponse(data=TranscribeResult(text=text, detected_language=detected_language))


@router.post(
    "/speak",
    summary="Synthesize speech audio (MP3) for a piece of text (text-to-speech)",
    responses={200: {"content": {"audio/mpeg": {}}}},
)
async def speak(
    payload: SpeakRequest,
    current_user: User = Depends(get_current_active_user),
    svc: ChatService = Depends(_svc),
) -> Response:
    audio_bytes = svc.synthesize_speech(payload.text, payload.language)
    return Response(content=audio_bytes, media_type="audio/mpeg")
