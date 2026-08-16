"""The MEVA local-AI agent loop.

Wires a local Ollama model up to MEVA's existing read-only tools:

  User question
      -> local model (may request a tool, in plain tool-calling mode)
      -> MEVA validates + runs the existing tool function
      -> tool result goes back to the model
      -> once evidence-gathering is done, ONE final structured call asks
         the model for a human-readable answer PLUS a list of the
         specific claims that answer makes (an AgentAnswer)

The agent never talks to FHIR data directly, and it never decides for
itself whether its own claims are correct — that's MEVA's verification
layer (meva.verification), which checks the claims deterministically
against real evidence. This file only handles the conversation with the
local model.

Reproducibility / performance (see docs/reproducibility.md):
- temperature=0 and seed=42 are used by default for both phases, so the
  same question produces consistent tool choices and claims.
- "thinking" (the model's chain-of-thought) is left on by default during
  tool selection (TOOL_CALL_THINK), since turning it off risked worse
  tool choices, but is turned off for the final structured-claims call
  (FINAL_STRUCTURED_THINK) — that call doesn't need open-ended reasoning,
  and disabling it cuts its latency dramatically.
"""

import json

from pydantic import ValidationError

from meva.ai.ollama_client import ChatResponse, OllamaClient, RunMetrics
from meva.ai.tools import TOOL_SCHEMAS, call_tool
from meva.verification.models import CLAIM_CATEGORIES, AgentAnswer, MedicalClaim

MAX_TOOL_ROUNDS = 5

# MEVA "evaluation mode" defaults — see docs/reproducibility.md for why.
EVAL_TEMPERATURE = 0
EVAL_SEED = 42
TOOL_CALL_THINK = True
FINAL_STRUCTURED_THINK = False
KEEP_ALIVE = "5m"

SYSTEM_PROMPT = """You are MEVA, a medical evidence retrieval assistant.

Rules you must always follow:
- All patient records you can access are 100% SYNTHETIC (fake, computer-generated). Never claim any information belongs to a real person.
- Answer questions ONLY using evidence retrieved through your tools. Do not use outside medical knowledge to fill in gaps.
- Do NOT diagnose. Do NOT prescribe. Do NOT recommend treatment.
- Do NOT invent or guess information that isn't present in the tool results.
- If a tool returns no data (an empty list) or the patient/evidence isn't found, say so explicitly instead of guessing.
- When asked about a patient, look up the patient_id given in the question using the appropriate tool.
"""

_FINAL_ANSWER_CATEGORIES = ", ".join(CLAIM_CATEGORIES)
_FINAL_ANSWER_INSTRUCTION = (
    "Give your final answer now, using only the tool results above. Respond with JSON matching the "
    "required schema: 'answer' is a clear, human-readable answer to the original question. 'claims' is "
    "a list of the specific factual claims your answer makes (skip it, or leave it empty, if you made no "
    "factual claims). Each claim needs: 'text' (short plain-English statement), 'patient_id', "
    f"'category' (one of: {_FINAL_ANSWER_CATEGORIES}), and "
    "'assertion' (one of: present, absent, value, attribute, interpretation — use 'interpretation' for any "
    "opinion or clinical judgement rather than a plain recorded fact). "
    "IMPORTANT: 'value' MUST be filled in with the specific short term being claimed (e.g. 'Fish', "
    "'Metformin', '128/81 mmHg') whenever assertion is 'present', 'value', or 'attribute' — never leave it "
    "null in those cases. One claim per fact: if there are multiple allergies/medications/conditions, create "
    "one claim per item, each with its own 'value'. "
    "If you also state a metadata detail about one of those items (e.g. an allergy's criticality or clinical "
    "status, a medication's status or intent), make that a SEPARATE claim with assertion='attribute', the "
    "same 'value' identifying the item (e.g. 'Fish'), plus 'attribute' (the field name, e.g. 'criticality') "
    "and 'attribute_value' (the claimed value, e.g. 'low')."
)


def _tool_calls_from(message: dict) -> list[dict]:
    return message.get("tool_calls") or []


def _assess_claim_quality(raw_claim: dict) -> bool:
    """Check one raw (pre-parse) claim dict against MEVA's structured-claim rules.

    This is a quality *measurement*, not a repair step — an invalid claim
    here is still dropped by _parse_agent_answer, never silently fixed.
    Returns True only if every check passes.
    """
    if not isinstance(raw_claim, dict):
        return False

    try:
        claim = MedicalClaim(**raw_claim)
    except (TypeError, ValidationError):
        return False  # claim_schema_valid: False

    if claim.category not in CLAIM_CATEGORIES:
        return False  # claim_category_valid: False

    if claim.assertion in ("present", "value", "attribute") and not claim.value:
        return False  # claim_value_present_when_required: False

    if claim.assertion == "attribute" and not (claim.attribute and claim.attribute_value):
        return False  # claim_attribute_valid: False

    return True


def _parse_agent_answer(content: str) -> tuple[AgentAnswer, dict]:
    """Parse the model's structured final response, tolerating a small local model's mistakes.

    A malformed claim is dropped rather than crashing the whole answer —
    the human-readable `answer` text is preserved either way. Also
    returns claim-quality stats (see _assess_claim_quality) — MEVA never
    silently repairs a malformed claim just to make this number look better.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return AgentAnswer(answer=content, claims=[]), _claim_quality_stats([], schema_parsed=False)

    if not isinstance(data, dict) or "answer" not in data:
        return AgentAnswer(answer=content, claims=[]), _claim_quality_stats([], schema_parsed=False)

    answer_text = data.get("answer") or content
    raw_claims = data.get("claims") or []

    claims = []
    for raw_claim in raw_claims:
        try:
            claims.append(MedicalClaim(**raw_claim))
        except (TypeError, ValidationError):
            continue

    return AgentAnswer(answer=answer_text, claims=claims), _claim_quality_stats(raw_claims, schema_parsed=True)


def _malformed_attribute_claim(raw_claim: dict) -> bool:
    """A claim that asserts 'attribute' but is missing attribute/attribute_value or is otherwise invalid."""
    if not isinstance(raw_claim, dict) or raw_claim.get("assertion") != "attribute":
        return False
    return not _assess_claim_quality(raw_claim)


def _wrong_category_or_assertion(raw_claim: dict) -> bool:
    """A claim whose category or assertion isn't one MEVA recognizes at all."""
    if not isinstance(raw_claim, dict):
        return True
    if raw_claim.get("category") not in CLAIM_CATEGORIES:
        return True
    if raw_claim.get("assertion") not in ("present", "absent", "value", "attribute", "interpretation"):
        return True
    return False


def _claim_quality_stats(raw_claims: list, schema_parsed: bool = True) -> dict:
    """schema_parsed: whether the model's raw content was valid JSON matching the top-level
    AgentAnswer shape (has an 'answer' key) — independent of whether individual claims were
    valid. Used to detect structured-output support (see meva.models / compatibility checks)."""
    total = len(raw_claims)
    valid = sum(1 for c in raw_claims if _assess_claim_quality(c))
    return {
        "schema_parsed": schema_parsed,
        "total_raw_claims": total,
        "valid_claims": valid,
        "structured_claim_validity_rate": (valid / total) if total else None,
        "malformed_attribute_claim_count": sum(1 for c in raw_claims if _malformed_attribute_claim(c)),
        "wrong_category_or_assertion_count": sum(1 for c in raw_claims if _wrong_category_or_assertion(c)),
    }


def _final_structured_answer(
    client: OllamaClient, messages: list[dict], temperature: float, seed: int, think: bool,
) -> tuple[AgentAnswer, RunMetrics, dict]:
    schema = AgentAnswer.model_json_schema()
    final_messages = [*messages, {"role": "user", "content": _FINAL_ANSWER_INSTRUCTION}]
    response: ChatResponse = client.chat(
        final_messages, tools=None, format=schema,
        think=think, temperature=temperature, seed=seed, keep_alive=KEEP_ALIVE,
    )
    agent_answer, claim_quality = _parse_agent_answer(response.message.get("content", ""))
    return agent_answer, response.metrics, claim_quality


def run_agent(
    question: str,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = EVAL_TEMPERATURE,
    seed: int = EVAL_SEED,
    tool_call_think: bool = TOOL_CALL_THINK,
    final_structured_think: bool = FINAL_STRUCTURED_THINK,
) -> dict:
    """Run one question through the agent loop.

    Returns {"answer": str, "claims": list[MedicalClaim], "log": list[dict], "metrics": dict,
    "claim_quality": dict}. "metrics" has "tool_calls" (a list of RunMetrics, one per
    tool-calling round) and "final" (the RunMetrics for the structured final call).
    "claim_quality" has "total_raw_claims", "valid_claims", and
    "structured_claim_validity_rate" (None if the model made zero claims).
    """
    client = OllamaClient(base_url=base_url, model=model)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    log = []
    tool_call_metrics = []

    for _round in range(MAX_TOOL_ROUNDS):
        response: ChatResponse = client.chat(
            messages, tools=TOOL_SCHEMAS,
            think=tool_call_think, temperature=temperature, seed=seed, keep_alive=KEEP_ALIVE,
        )
        tool_call_metrics.append(response.metrics)
        message = response.message
        messages.append(message)

        tool_calls = _tool_calls_from(message)
        if not tool_calls:
            break

        for call in tool_calls:
            name = call["function"]["name"]
            arguments = call["function"].get("arguments") or {}

            try:
                result = call_tool(name, arguments)
                error = None
            except ValueError as e:
                result = {"error": str(e)}
                error = str(e)

            log.append({
                "model": client.model,
                "question": question,
                "tool": name,
                "arguments": arguments,
                "result": result,
                "error": error,
            })

            messages.append({"role": "tool", "content": json.dumps(result)})

    agent_answer, final_metrics, claim_quality = _final_structured_answer(
        client, messages, temperature=temperature, seed=seed, think=final_structured_think,
    )

    return {
        "answer": agent_answer.answer,
        "claims": agent_answer.claims,
        "log": log,
        "metrics": {"tool_calls": tool_call_metrics, "final": final_metrics},
        "claim_quality": claim_quality,
    }
