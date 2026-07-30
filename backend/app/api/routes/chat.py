from functools import lru_cache

from fastapi import APIRouter

from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.services.chatbot import PolicyChatbot

router = APIRouter(tags=["chat"])


@lru_cache
def get_chatbot() -> PolicyChatbot:
    return PolicyChatbot()


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    return get_chatbot().answer(payload.message)
