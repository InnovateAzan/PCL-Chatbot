from fastapi import APIRouter

from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.services.chatbot import PolicyChatbot

router = APIRouter(tags=["chat"])
chatbot = PolicyChatbot()


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    return chatbot.answer(payload.message)
