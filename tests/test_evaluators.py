"""Unit tests for the deterministic eval evaluators (no LLM involved)."""

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.otel._errors import SpanTreeRecordingError

from app.agent.triage import TriageResult
from app.models import TicketCategory, TicketPriority
from evals.dataset import Expectation, TriageInput
from evals.evaluators import (
    OutageDetected,
    PriorityMatches,
    ReplyLanguageMatches,
    TriageRun,
    detect_language,
)
from evals.run import _inspect_tools


def _ctx(expected: Expectation, run: TriageRun) -> EvaluatorContext:
    return EvaluatorContext(
        name="case",
        inputs=TriageInput(subject="s", body="b", customer_email="a@example.com"),
        metadata=None,
        expected_output=expected,
        output=run,
        duration=0.0,
        _span_tree=SpanTreeRecordingError("not recorded"),
        attributes={},
        metrics={},
    )


def _run(priority: TicketPriority, reply: str, similar: int = 0) -> TriageRun:
    result = TriageResult(
        priority=priority, category=TicketCategory.ACCOUNT, summary="s", suggested_reply=reply
    )
    return TriageRun(result=result, similar_tickets_found=similar)


def test_detect_language() -> None:
    assert detect_language("Hola, gracias por escribirnos. Nuestro equipo lo revisará.") == "es"
    assert detect_language("Hello, thank you for reaching out. Our team will review it.") == "en"


def test_priority_accepts_any_expected_value() -> None:
    expected = Expectation((TicketPriority.HIGH, TicketPriority.URGENT), (), "es")

    assert PriorityMatches().evaluate(_ctx(expected, _run(TicketPriority.URGENT, "x"))).value
    assert not PriorityMatches().evaluate(_ctx(expected, _run(TicketPriority.LOW, "x"))).value


def test_reply_language_mismatch_fails() -> None:
    expected = Expectation((), (), "en")
    run = _run(TicketPriority.LOW, "Hola, gracias por escribirnos. Lo revisaremos.")

    assert not ReplyLanguageMatches().evaluate(_ctx(expected, run)).value


def test_outage_detected_only_applies_to_outage_cases() -> None:
    not_outage = Expectation((), (), "es", outage=False)
    outage = Expectation((), (), "es", outage=True)

    assert OutageDetected().evaluate(_ctx(not_outage, _run(TicketPriority.LOW, "x"))) == {}
    missed = OutageDetected().evaluate(_ctx(outage, _run(TicketPriority.LOW, "x", similar=0)))
    found = OutageDetected().evaluate(_ctx(outage, _run(TicketPriority.LOW, "x", similar=3)))
    assert missed["OutageDetected"].value is False
    assert found["OutageDetected"].value is True


def test_inspect_tools_counts_similar_tickets() -> None:
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart("get_customer_history", {}),
                ToolCallPart("search_similar_tickets", {"keywords": "login"}),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart("get_customer_history", []),
                ToolReturnPart("search_similar_tickets", [{"id": 1}, {"id": 2}]),
            ]
        ),
        ModelResponse(parts=[ToolCallPart("final_result", {})]),
    ]

    tools, similar = _inspect_tools(messages)

    assert tools == ["get_customer_history", "search_similar_tickets"]
    assert similar == 2
