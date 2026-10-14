"""Run the triage evals against the real model.

    uv run python -m evals.run                      # all cases
    uv run python -m evals.run --cases outage_login,outage_login_no_accents
    uv run python -m evals.run --min-pass-rate 0.9

Exits with status 1 when the assertion pass rate is below the threshold or a case
crashed, so CI can gate on it. Needs GOOGLE_API_KEY.
"""

import argparse
import os
import sys
from dataclasses import asdict

from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart
from pydantic_ai.retries import RetryConfig
from pydantic_evals import Dataset
from pydantic_evals.evaluators import Evaluator, LLMJudge
from pydantic_evals.reporting import EvaluationReport
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from tenacity import stop_after_attempt, wait_exponential

from app.agent.triage import TriageResult, run_triage
from app.config import settings
from app.schemas import TicketCreate
from app.services.tickets import create_ticket
from evals.dataset import CASES, TriageInput
from evals.evaluators import TriageRun, build_evaluators
from scripts.seed import SAMPLE_TICKETS


def _inspect_tools(messages: list[ModelMessage]) -> tuple[list[str], int]:
    tools_called: list[str] = []
    similar_found = 0
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name != "final_result":
                tools_called.append(part.tool_name)
            if isinstance(part, ToolReturnPart) and part.tool_name == "search_similar_tickets":
                similar_found = max(similar_found, len(part.content or []))
    return tools_called, similar_found


async def triage_task(inputs: TriageInput) -> TriageRun:
    """Triage one case in a fresh in-memory DB seeded with the sample tickets."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for sample in SAMPLE_TICKETS:
            if sample.subject != inputs.subject:
                create_ticket(session, sample)
        ticket = create_ticket(session, TicketCreate(**asdict(inputs)))

        with capture_run_messages() as messages:
            result = await run_triage(session, ticket)

    tools_called, similar_found = _inspect_tools(messages)
    return TriageRun(result=result, tools_called=tools_called, similar_tickets_found=similar_found)


# On top of the HTTP-level retries in build_model: rides out provider overloads that last
# longer than a few seconds (Gemini 503 "high demand" spikes) before giving up.
PROVIDER_OUTAGE_RETRY = RetryConfig(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=10, max=60),
    reraise=True,
)

CALIBRATION_REPLIES = {
    # (reply, should the judge pass it?)
    "fabricated_steps": (
        "Hello! To change your profile picture, go to your account settings and open the "
        "profile section.",
        False,
    ),
    "safe_reply": (
        "Hello! Thanks for reaching out. Our team will review your question and get back to "
        "you soon.",
        True,
    ),
}


def calibrate_judge(judge: Evaluator) -> None:
    """Grade replies with a known verdict first: a judge that gets these wrong can't be trusted."""
    case = CASES[0]
    for label, (reply, expected) in CALIBRATION_REPLIES.items():
        output = TriageRun(
            result=TriageResult(
                priority="low", category="other", summary="calibration", suggested_reply=reply
            )
        )

        async def fixed_output(_: TriageInput, output: TriageRun = output) -> TriageRun:
            return output

        report = Dataset(name="judge_calibration", cases=[case], evaluators=[judge]).evaluate_sync(
            fixed_output, progress=False, retry_evaluators=PROVIDER_OUTAGE_RETRY
        )
        verdicts = [a.value for c in report.cases for a in c.assertions.values()]
        if verdicts != [expected]:
            sys.exit(f"Judge calibration failed on '{label}': expected {expected}, got {verdicts}")
    print("Judge calibration passed.")


def pass_rate(report: EvaluationReport) -> float:
    results = [r.value is True for case in report.cases for r in case.assertions.values()]
    return sum(results) / len(results) if results else 0.0


def write_github_summary(report: EvaluationReport, rate: float, threshold: float) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    names = sorted({name for case in report.cases for name in case.assertions})
    lines = [
        f"## Triage evals: {rate:.0%} pass rate (threshold {threshold:.0%})",
        f"Agent model `{settings.ai_model}` · judge `{settings.eval_judge_model}`",
        "",
        "| Case | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]
    for case in report.cases:
        cells = []
        for name in names:
            result = case.assertions.get(name)
            cells.append("—" if result is None else ("✅" if result.value is True else "❌"))
        lines.append(f"| {case.name} | " + " | ".join(cells) + " |")
    for failure in report.failures:
        lines.append(f"| {failure.name} | crashed: {failure.error_message} |")
    for case in report.cases:
        for error in case.evaluator_failures:
            lines.append(f"| {case.name} | `{error.name}` errored: {error.error_message} |")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", help="comma-separated case names (default: all)")
    parser.add_argument("--min-pass-rate", type=float, default=0.85)
    args = parser.parse_args()

    cases = CASES
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [case for case in CASES if case.name in wanted]
        if unknown := wanted - {case.name for case in cases}:
            sys.exit(f"Unknown cases: {sorted(unknown)}")

    evaluators = build_evaluators()
    calibrate_judge(next(e for e in evaluators if isinstance(e, LLMJudge)))

    dataset = Dataset(name="triage", cases=cases, evaluators=evaluators)
    # One case at a time keeps us inside free-tier rate limits.
    report = dataset.evaluate_sync(
        triage_task,
        max_concurrency=1,
        name=settings.ai_model,
        retry_task=PROVIDER_OUTAGE_RETRY,
        retry_evaluators=PROVIDER_OUTAGE_RETRY,
    )
    report.print(include_reasons=True, include_durations=False)

    rate = pass_rate(report)
    write_github_summary(report, rate, args.min_pass_rate)
    # A check that errored (e.g. the judge hit a rate limit) must not count as passing.
    evaluator_errors = sum(len(case.evaluator_failures) for case in report.cases)
    print(f"\nAssertion pass rate: {rate:.0%} (threshold {args.min_pass_rate:.0%})")
    print(f"Crashed cases: {len(report.failures)} · evaluator errors: {evaluator_errors}")
    if report.failures or evaluator_errors or rate < args.min_pass_rate:
        sys.exit(1)


if __name__ == "__main__":
    main()
