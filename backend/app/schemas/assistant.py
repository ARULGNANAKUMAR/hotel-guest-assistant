import re
from typing import Any, Optional
from pydantic import BaseModel, field_validator, model_validator


class ConversationContext(BaseModel):
    """Simple request-level context carrying extracted guest availability info."""
    checkIn: Optional[str] = None
    checkOut: Optional[str] = None
    adults: Optional[int] = None
    last_intent: Optional[str] = None

    @model_validator(mode="after")
    def validate_fields(self) -> "ConversationContext":
        iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if self.checkIn is not None and not iso_re.match(self.checkIn):
            self.checkIn = None  # silently drop invalid value — must not crash
        if self.checkOut is not None and not iso_re.match(self.checkOut):
            self.checkOut = None
        if self.adults is not None and self.adults <= 0:
            self.adults = None
        return self


class AssistantRequest(BaseModel):
    message: str
    context: Optional[ConversationContext] = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty")
        if len(v) > 2000:
            raise ValueError("message must not exceed 2000 characters")
        return v

    @model_validator(mode="before")
    @classmethod
    def coerce_context(cls, values: Any) -> Any:
        """
        Accept either a ConversationContext object or a plain dict (from JSON).
        Invalid or non-dict context is silently dropped so the API never crashes.
        """
        ctx = values.get("context") if isinstance(values, dict) else getattr(values, "context", None)
        if ctx is None or isinstance(ctx, ConversationContext):
            return values
        if isinstance(ctx, dict):
            try:
                values["context"] = ConversationContext(**ctx)
            except Exception:
                values["context"] = None
        else:
            if isinstance(values, dict):
                values["context"] = None
        return values


class AssistantResponse(BaseModel):
    message: str
    type: str = "text"
    requires_input: bool = False
    data: Optional[Any] = None
    context: Optional[ConversationContext] = None  # echo merged context back to client
