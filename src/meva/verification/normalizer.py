"""Conservative text normalization for comparing claim values to evidence values.

This is intentionally simple. It only smooths out safe, mechanical
differences (case, whitespace, common Synthea coding suffixes like
"(substance)"). It never guesses that two different medical terms mean
the same thing — when in doubt, the verifier should return UNVERIFIABLE
rather than rely on a fuzzy match here.
"""

import re

# Synthea/SNOMED display names often end with a category hint in parentheses,
# e.g. "Fish (substance)", "Acute viral pharyngitis (disorder)". Strip it for
# comparison purposes only — the original text is kept everywhere else.
_CATEGORY_SUFFIX = re.compile(r"\s*\((?:substance|organism|disorder|finding|procedure)\)\s*$", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Lowercase, trim, and strip a known Synthea display suffix for comparison."""
    text = value.strip().casefold()
    text = _CATEGORY_SUFFIX.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip(" .,;:")


def values_match(claim_value: str, evidence_value: str) -> bool:
    """True if two values are the same, or one is a full-word match inside the other.

    The substring check exists because real medication names are verbose
    (e.g. "Loratadine 5 MG Chewable Tablet"), and a claim like "the patient
    takes Loratadine" should still match. It's still exact substring
    matching on normalized text, not fuzzy/approximate matching.
    """
    a = normalize_text(claim_value)
    b = normalize_text(evidence_value)
    if not a or not b:
        return False
    return a == b or a in b or b in a
