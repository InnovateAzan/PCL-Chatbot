from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = Field(default=None, alias="sessionId")
    session_uuid: str | None = Field(default=None, alias="sessionUuid")
    user_email: str | None = Field(default=None, alias="userEmail", max_length=320)
    display_name: str | None = Field(default=None, alias="displayName", max_length=255)
    display_name_snake: str | None = Field(
        default=None,
        alias="display_name",
        max_length=255,
        exclude=True,
    )
    preferred_name: str | None = Field(
        default=None,
        alias="preferredName",
        max_length=255,
    )
    department: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(populate_by_name=True)

    @property
    def resolved_display_name(self) -> str | None:
        return self.display_name or self.display_name_snake


class SourceReference(BaseModel):
    document_name: str
    section: str | None = None
    page_number: int | None = None
    snippet: str | None = None
    chunk_id: str | None = None
    similarity_score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)
    fallback: bool = False
    provider: str = "policy-rules"
    notice: str | None = None
    user_message_id: int | None = Field(default=None, alias="userMessageId")
    assistant_message_id: int | None = Field(
        default=None,
        alias="assistantMessageId",
    )
    response_source: str | None = Field(default=None, alias="responseSource")
    session_id: int | str | None = Field(default=None, alias="sessionId")
    session_uuid: str | None = Field(default=None, alias="sessionUuid")

    model_config = ConfigDict(populate_by_name=True)


class LegacyFeedbackRequest(BaseModel):
    message_id: int = Field(alias="message_id")
    rating: str
    comments: str | None = None
    user_email: str | None = Field(default=None, alias="user_email")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"helpful", "not_helpful", "partially_helpful"}
        if normalized not in allowed:
            raise ValueError("Rating must be helpful, not_helpful, or partially_helpful.")
        return normalized


class LegacyFeedbackResponse(BaseModel):
    id: int | None = None
    message_id: int = Field(alias="messageId")
    rating: str
    saved: bool = True

    model_config = ConfigDict(populate_by_name=True)


class UserInitializeRequest(BaseModel):
    display_name: str = Field(alias="displayName", min_length=1, max_length=255)
    preferred_name: str | None = Field(
        default=None,
        alias="preferredName",
        max_length=255,
    )
    email: EmailStr
    employee_id: str | None = Field(
        default=None,
        alias="employeeId",
        max_length=100,
    )
    department: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, alias="jobTitle", max_length=255)
    entra_object_id: str | None = Field(
        default=None,
        alias="entraObjectId",
        max_length=255,
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator(
        "display_name",
        "preferred_name",
        "employee_id",
        "department",
        "job_title",
        "entra_object_id",
        mode="before",
    )
    @classmethod
    def trim_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None

        trimmed = str(value).strip()
        return trimmed or None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserProfileResponse(BaseModel):
    id: int
    entra_object_id: str | None = Field(alias="entraObjectId")
    employee_id: str | None = Field(alias="employeeId")
    display_name: str = Field(alias="displayName")
    preferred_name: str | None = Field(alias="preferredName")
    email: str
    department: str | None
    job_title: str | None = Field(alias="jobTitle")
    is_active: bool = Field(alias="isActive")
    first_seen_at: datetime = Field(alias="firstSeenAt")
    last_seen_at: datetime = Field(alias="lastSeenAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserInitializeResponse(BaseModel):
    user_id: int = Field(alias="userId")
    profile: UserProfileResponse

    model_config = ConfigDict(populate_by_name=True)


class CreateChatSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ChatSessionResponse(BaseModel):
    id: UUID
    user_id: int = Field(alias="userId")
    title: str | None
    status: str
    started_at: datetime = Field(alias="startedAt")
    ended_at: datetime | None = Field(alias="endedAt")
    message_count: int = Field(alias="messageCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CreateChatSessionResponse(BaseModel):
    session_id: UUID = Field(alias="sessionId")
    session: ChatSessionResponse

    model_config = ConfigDict(populate_by_name=True)


class PaginatedChatSessionsResponse(BaseModel):
    items: list[ChatSessionResponse]
    limit: int
    offset: int
    total: int


class ChatMessageResponse(BaseModel):
    id: int
    session_id: UUID = Field(alias="sessionId")
    user_id: int = Field(alias="userId")
    role: str
    message_text: str = Field(alias="messageText")
    response_source: str | None = Field(alias="responseSource")
    model_name: str | None = Field(alias="modelName")
    response_time_ms: int | None = Field(alias="responseTimeMs")
    fallback_used: bool = Field(alias="fallbackUsed")
    created_at: datetime = Field(alias="createdAt")
    metadata_json: dict | None = Field(alias="metadataJson")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginatedChatMessagesResponse(BaseModel):
    items: list[ChatMessageResponse]
    limit: int
    offset: int
    total: int


class MessageSourceResponse(BaseModel):
    id: int
    assistant_message_id: int = Field(alias="assistantMessageId")
    document_name: str = Field(alias="documentName")
    section_name: str | None = Field(alias="sectionName")
    page_number: int | None = Field(alias="pageNumber")
    chunk_id: str | None = Field(alias="chunkId")
    similarity_score: float | None = Field(alias="similarityScore")
    source_order: int = Field(alias="sourceOrder")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageSourcesResponse(BaseModel):
    items: list[MessageSourceResponse]


class FeedbackRequest(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    feedback_type: str = Field(alias="feedbackType", max_length=30)
    comments: str | None = Field(default=None, max_length=5000)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("feedback_type")
    @classmethod
    def normalize_feedback_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {
            "HELPFUL",
            "NOT_HELPFUL",
            "INCORRECT",
            "INCOMPLETE",
            "WRONG_POLICY",
            "OTHER",
        }

        if normalized not in allowed:
            raise ValueError("Invalid feedback type.")

        return normalized


class FeedbackResponse(BaseModel):
    id: int
    assistant_message_id: int = Field(alias="assistantMessageId")
    user_id: int = Field(alias="userId")
    rating: int | None
    feedback_type: str = Field(alias="feedbackType")
    comments: str | None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UnansweredQuestionResponse(BaseModel):
    id: int
    user_message_id: int = Field(alias="userMessageId")
    normalized_question: str = Field(alias="normalizedQuestion")
    detected_topic: str | None = Field(alias="detectedTopic")
    occurrence_count: int = Field(alias="occurrenceCount")
    review_status: str = Field(alias="reviewStatus")
    reviewed_by: str | None = Field(alias="reviewedBy")
    reviewed_at: datetime | None = Field(alias="reviewedAt")
    improvement_notes: str | None = Field(alias="improvementNotes")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PaginatedUnansweredQuestionsResponse(BaseModel):
    items: list[UnansweredQuestionResponse]
    limit: int
    offset: int
    total: int


class UpdateUnansweredQuestionRequest(BaseModel):
    review_status: str | None = Field(default=None, alias="reviewStatus")
    reviewed_by: str | None = Field(default=None, alias="reviewedBy", max_length=255)
    improvement_notes: str | None = Field(
        default=None,
        alias="improvementNotes",
        max_length=5000,
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("review_status")
    @classmethod
    def normalize_review_status(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().upper()
        if normalized not in {"PENDING", "REVIEWED", "RESOLVED", "IGNORED"}:
            raise ValueError("Invalid review status.")

        return normalized


class AnalyticsSummaryResponse(BaseModel):
    total_users: int = Field(alias="totalUsers")
    active_users: int = Field(alias="activeUsers")
    total_chat_sessions: int = Field(alias="totalChatSessions")
    total_user_questions: int = Field(alias="totalUserQuestions")
    total_assistant_responses: int = Field(alias="totalAssistantResponses")
    policy_based_responses: int = Field(alias="policyBasedResponses")
    general_ai_responses: int = Field(alias="generalAiResponses")
    onedesk_live_data_responses: int = Field(alias="onedeskLiveDataResponses")
    fallback_responses: int = Field(alias="fallbackResponses")
    unanswered_questions: int = Field(alias="unansweredQuestions")
    feedback_count: int = Field(alias="feedbackCount")
    average_feedback_rating: float | None = Field(alias="averageFeedbackRating")
    helpful_percentage: float | None = Field(alias="helpfulPercentage")
    average_response_time_ms: float | None = Field(alias="averageResponseTimeMs")

    model_config = ConfigDict(populate_by_name=True)


class AnalyticsSeriesItem(BaseModel):
    label: str
    value: int | float


class AnalyticsListResponse(BaseModel):
    items: list[dict]
    limit: int | None = None
    offset: int | None = None
    total: int | None = None


class OneDeskRecordResponse(BaseModel):
    module: str
    request_number: str | None = Field(alias="requestNumber")
    title: str | None
    status: str | None
    assigned_to: str | None = Field(alias="assignedTo")
    updated_at: str | None = Field(alias="updatedAt")
    latest_update: str | None = Field(alias="latestUpdate")

    model_config = ConfigDict(populate_by_name=True)


class HealthResponse(BaseModel):
    status: str
    details: dict = Field(default_factory=dict)
