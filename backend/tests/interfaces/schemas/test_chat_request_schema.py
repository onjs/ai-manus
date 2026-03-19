import pytest
from pydantic import ValidationError

from app.interfaces.schemas.session import ChatRequest


def test_chat_request_requires_request_id_when_message_exists():
    with pytest.raises(ValidationError) as err:
        ChatRequest(message="hello")
    assert "request_id is required when message is provided" in str(err.value)


def test_chat_request_rejects_invalid_event_id():
    with pytest.raises(ValidationError) as err:
        ChatRequest(message="hello", request_id="req-1", event_id="invalid")
    assert "event_id must be a valid stream id" in str(err.value)


def test_chat_request_accepts_valid_contract():
    req = ChatRequest(message="hello", request_id="req-1", event_id="123-0")
    assert req.message == "hello"
    assert req.request_id == "req-1"
    assert req.event_id == "123-0"
