from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class SourceReference(BaseModel):
    document_name: str
    section: str | None = None
    page_number: int | None = None
    snippet: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)
    fallback: bool = False
    provider: str = "policy-rules"
    notice: str | None = None
