"""Evaluators: deterministic checks where possible, an LLM judge where judgment is needed."""

import re
from dataclasses import dataclass, field

from pydantic_ai.models.fallback import FallbackModel
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext, LLMJudge

from app.agent.triage import TriageResult, build_model
from app.config import settings
from evals.dataset import Expectation, TriageInput


@dataclass
class TriageRun:
    """Task output: the agent's result plus what it did to get there."""

    result: TriageResult
    tools_called: list[str] = field(default_factory=list)
    similar_tickets_found: int = 0


Ctx = EvaluatorContext[TriageInput, TriageRun, None]


@dataclass
class PriorityMatches(Evaluator[TriageInput, TriageRun, None]):
    def evaluate(self, ctx: Ctx) -> EvaluationReason:
        expected: Expectation = ctx.expected_output
        got = ctx.output.result.priority
        return EvaluationReason(
            value=got in expected.priorities,
            reason=f"got {got}, expected one of {[str(p) for p in expected.priorities]}",
        )


@dataclass
class CategoryMatches(Evaluator[TriageInput, TriageRun, None]):
    def evaluate(self, ctx: Ctx) -> EvaluationReason:
        expected: Expectation = ctx.expected_output
        got = ctx.output.result.category
        return EvaluationReason(
            value=got in expected.categories,
            reason=f"got {got}, expected one of {[str(c) for c in expected.categories]}",
        )


_STOPWORDS = {
    "es": {"el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "tu", "su", "para",
           "por", "con", "hola", "gracias", "nuestro", "equipo", "lo", "te", "se", "es"},
    "en": {"the", "and", "to", "you", "your", "we", "our", "of", "is", "for", "with", "hello",
           "hi", "thank", "thanks", "team", "it", "this", "that", "will"},
}


def detect_language(text: str) -> str:
    """Tiny stopword-based es/en detector: enough for multi-sentence replies."""
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    scores = {lang: sum(w in stop for w in words) for lang, stop in _STOPWORDS.items()}
    return max(scores, key=scores.__getitem__)


@dataclass
class ReplyLanguageMatches(Evaluator[TriageInput, TriageRun, None]):
    def evaluate(self, ctx: Ctx) -> EvaluationReason:
        expected: Expectation = ctx.expected_output
        got = detect_language(ctx.output.result.suggested_reply)
        return EvaluationReason(
            value=got == expected.reply_language,
            reason=f"reply detected as {got}, customer wrote in {expected.reply_language}",
        )


@dataclass
class OutageDetected(Evaluator[TriageInput, TriageRun, None]):
    """Only for outage cases: the search tool must surface the other reports."""

    min_similar: int = 2

    def evaluate(self, ctx: Ctx) -> dict[str, EvaluationReason]:
        expected: Expectation = ctx.expected_output
        if not expected.outage:
            return {}  # not applicable: no result instead of a free pass
        found = ctx.output.similar_tickets_found
        return {
            "OutageDetected": EvaluationReason(
                value=found >= self.min_similar,
                reason=f"search returned {found} similar tickets (need {self.min_similar})",
            )
        }


@dataclass
class ConsultedHistory(Evaluator[TriageInput, TriageRun, None]):
    def evaluate(self, ctx: Ctx) -> EvaluationReason:
        called = "get_customer_history" in ctx.output.tools_called
        return EvaluationReason(value=called, reason=f"tools called: {ctx.output.tools_called}")


NO_FABRICATION_RUBRIC = """\
Look only at `result.suggested_reply`, the reply that will be sent to the customer.
The agent knows nothing about the product beyond the customer's message.
PASS if the reply does not state as fact any specific information that is not in the
customer's message: plan contents, prices, refund or cancellation policies, feature
availability, concrete deadlines, or how to use the product (menus, settings, buttons,
step-by-step instructions). Acknowledging the problem, apologizing, saying the team will
review it or asking for details is fine.
FAIL if the reply confirms, denies or promises any such fact, or tells the customer where
to click or which settings to use.
"""


def build_evaluators() -> list[Evaluator[TriageInput, TriageRun, None]]:
    return [
        PriorityMatches(),
        CategoryMatches(),
        ReplyLanguageMatches(),
        OutageDetected(),
        ConsultedHistory(),
        LLMJudge(
            rubric=NO_FABRICATION_RUBRIC,
            include_input=True,
            # Prefer a judge that differs from the agent; if it is down, a fallback judge
            # beats losing the check entirely.
            model=FallbackModel(
                build_model(settings.eval_judge_model), build_model(settings.ai_model)
            ),
            assertion={"evaluation_name": "NoFabrication", "include_reason": True},
        ),
    ]
