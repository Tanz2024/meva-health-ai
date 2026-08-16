"""The claim-extraction prompt (Stage 7D1, hardened in Stage 7D2.1).

This is the entire instruction the extractor sees, besides the question,
patient_id, and the answer text itself — see meva.extraction.extractor for
the anti-leakage rule this prompt exists to support (no FHIR/evidence/
expected-result data is ever included in the extractor's input). The rules
and examples below are a direct restatement of docs/claim-extraction-contract.md
— see that document for the full rationale behind each one. Every example is
generic and synthetic; none names a specific gold/dev/holdout fixture or a
real benchmark case, so nothing here is tuned to a specific evaluation item.
"""

import hashlib

from meva.verification.models import CLAIM_CATEGORIES

_CATEGORIES = ", ".join(CLAIM_CATEGORIES)

# Bumped whenever EXTRACTION_SYSTEM_PROMPT's wording changes — recorded in every
# extraction report alongside prompt_hash() so results stay attributable to the
# exact prompt that produced them (see docs/decoupled-evaluation.md,
# docs/claim-extraction-contract.md). Stage 7D2.1 hardened the Stage 7D1 prompt
# with explicit assertion-semantics rules and generalized examples.
EXTRACTION_PROMPT_VERSION = "v2-stage7d2.1"

EXTRACTION_SYSTEM_PROMPT = f"""You are a claim-extraction tool. You are given a question about a \
patient's medical record and a natural-language answer someone else already wrote. Your ONLY job \
is to represent, as structured claims, the factual medical-record statements that answer ACTUALLY \
CONTAINS — nothing more.

GENERAL RULES:
- Extract only claims that are explicitly stated in the answer text. Do not add facts.
- Do not correct the answer, even if you believe it is wrong or incomplete. Preserve it exactly as stated.
- Do not consult outside medical knowledge. You have no access to the patient's real record.
- Do not infer missing information the answer doesn't state.
- If the answer contains no factual medical-record claim at all (e.g. it only says the patient wasn't found,
  or asks a question back), return zero claims. Zero claims is a valid, expected result.
- Every claim's category must be one of: {_CATEGORIES}.
- Every claim's patient_id must be the patient_id given to you — never invent a different one.
- One independently-checkable fact = one claim. Do not collapse multiple facts into one vague claim,
  and do not split one fact into several redundant claims.

ASSERTION TYPES — use exactly the right one:

1. "present" — a specific named item exists (an allergy/medication/condition/encounter).
   Example: "Fish allergy is recorded." -> category=allergy, assertion=present, value=Fish

2. "absent", GLOBAL (category-wide) — the answer says an ENTIRE category has nothing recorded,
   without naming any specific item. value is null.
   Example: "No allergies are recorded." -> category=allergy, assertion=absent, value=null

3. "absent", ITEM-SPECIFIC — the answer names a SPECIFIC item and says it is not recorded.
   value is that item's name, even though the assertion is "absent".
   Example: "No Penicillin allergy is recorded." -> category=allergy, assertion=absent, value=Penicillin

4. "value" — a specific recorded reading or demographic value (not "this item exists", but
   "this item's value is exactly X"). For an observation with a name and reading, value must be
   "<Observation Name>: <reading with units>" (e.g. "Heart Rate: 72 bpm"). For a demographic fact,
   value is just the stated value (e.g. "female") with category=patient.
   Example: "Heart rate is 72 bpm." -> category=observation, assertion=value, value="Heart Rate: 72 bpm"

5. "attribute" — a metadata field of an ALREADY-NAMED item: value is which item, attribute is the
   field name, attribute_value is its claimed value. Known attribute fields: allergy
   criticality/clinical_status; medication status/intent; condition clinical_status/onset.
   Example: "The Fish allergy has low criticality." ->
     category=allergy, assertion=attribute, value=Fish, attribute=criticality, attribute_value=low

6. "interpretation" — ONLY an actual clinical judgement/opinion stated in the answer (e.g. "this
   looks concerning"). Never use this for an objective fact just because it's easier — a checkable
   fact must use present/absent/value/attribute instead.

UNCERTAINTY: if the answer hedges a statement ("may", "might", "possibly", "appears to", "it's
unclear whether..."), do NOT convert it into a definite claim of any kind. Produce zero claims for
that specific proposition. Do not guess whether the hedge means yes or no.

You are not being asked whether the answer is correct. You are only being asked what it says.
"""

EXTRACTION_INSTRUCTION_TEMPLATE = (
    "Question: {question}\n"
    "Patient ID: {patient_id}\n"
    "Answer to extract claims from:\n{answer_text}\n\n"
    "Respond with JSON matching the required schema: 'claims' is a list of the specific claims "
    "actually stated in the answer above (each with category, value, assertion, and patient_id={patient_id}; "
    "use attribute/attribute_value only for assertion=\"attribute\" claims). Return an empty list if the "
    "answer states no factual medical-record claim."
)


def prompt_hash() -> str:
    """SHA-256 of the exact, current extraction system prompt text — recorded in every
    extraction report so results stay attributable to the exact prompt that produced them."""
    return hashlib.sha256(EXTRACTION_SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def build_extraction_messages(question: str, patient_id: str, answer_text: str) -> list[dict]:
    """The exact, complete message list sent to the extractor.

    Deliberately contains nothing but the question, patient_id, and answer
    text — see meva.extraction.extractor.ALLOWED_EXTRACTOR_INPUT_FIELDS.
    """
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": EXTRACTION_INSTRUCTION_TEMPLATE.format(
            question=question, patient_id=patient_id, answer_text=answer_text,
        )},
    ]
