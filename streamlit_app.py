"""MEVA Browser Sandbox (Stage 8C) — a Streamlit UI over MEVA's real,
deterministic evidence verifier and the public v0.4 synthetic dataset.

This file is intentionally thin: every piece of actual logic (listing
patients, describing them, verifying a claim, picking a display value for a
composite observation) lives in meva.playground.service, the same module
the Stage 8B CLI (examples/playground.py) uses. This file only builds the
UI and calls that service — it implements no verification rules of its own.

No AI model inference happens anywhere in this app (no Ollama, no
qwen3:4b/llama3.2:3b, no claim extraction) and it makes no outbound network
calls of any kind — everything needed is packaged with the repository. See
docs/playground.md, "Browser Sandbox" for the full picture.

Run locally (after `pip install -e ".[playground]"`):
    streamlit run streamlit_app.py
"""

import streamlit as st
from pydantic import ValidationError

from meva.playground import (
    build_ready_made_examples,
    describe_patient,
    list_patients,
    observation_display_value,
    verify_claim,
)
from meva.mcp import server as mcp_server
from meva.verification.models import CLAIM_ASSERTIONS, CLAIM_CATEGORIES, MedicalClaim

STATUS_EXPLANATIONS = {
    "SUPPORTED": "Retrieved evidence supports the structured claim.",
    "CONTRADICTED": "Retrieved evidence directly conflicts with the structured claim.",
    "UNSUPPORTED": "MEVA found no retrieved evidence supporting that factual assertion.",
    "UNVERIFIABLE": "MEVA's current deterministic rules cannot safely evaluate the claim.",
}

# Streamlit's icon param wants an emoji/path, not a clinical symbol — kept neutral.
st.set_page_config(page_title="MEVA Sandbox", page_icon="🧪", layout="wide")


# --- cached, read-only helpers (safe: no user input, no sensitive data) -----

@st.cache_data(show_spinner=False)
def _cached_patient_list() -> list[dict]:
    return list_patients()


@st.cache_data(show_spinner=False)
def _cached_patient_summary(patient_id: str) -> dict:
    return describe_patient(patient_id)


@st.cache_data(show_spinner=False)
def _cached_ready_made_examples() -> list[dict]:
    return build_ready_made_examples()


# --- header ------------------------------------------------------------

st.title("MEVA")
st.subheader("Medical Evidence Verification Agent")
st.caption("Explore how MEVA checks AI-style claims against synthetic FHIR evidence.")

st.warning(
    "**Synthetic data only. Not medical advice. Not for diagnosis or treatment.** "
    "Every patient here is fictional (Synthea-generated) — see the Privacy section below.",
    icon="⚠️",
)

with st.expander("How this sandbox works (5 steps)", expanded=False):
    st.markdown(
        "1. **Select a synthetic patient**\n"
        "2. **Inspect the recorded evidence** — allergies, medications, conditions, observations\n"
        "3. **Build a claim** — a structured statement about that patient's record\n"
        "4. **Ask MEVA to verify it** — using MEVA's real, deterministic verifier (no AI model)\n"
        "5. **Inspect the provenance** — exactly which recorded fact produced the verdict"
    )

st.divider()

# --- patient selector -----------------------------------------------------

st.header("1. Select a synthetic patient")

patients = _cached_patient_list()
patient_options = {f"{p['name']} — {p['patient_id']}": p["patient_id"] for p in patients}
label_by_patient_id = {v: k for k, v in patient_options.items()}
labels = list(patient_options.keys())

if not labels:
    st.error(
        "MEVA could not load the public synthetic patient dataset. "
        "Please check the deployment configuration."
    )
    st.stop()

if "patient_selector" not in st.session_state:
    st.session_state["patient_selector"] = labels[0]

selected_label = st.selectbox(
    "Synthetic patient", options=labels, key="patient_selector",
    help="All patients are fictional, Synthea-generated data — search by name or ID.",
)
selected_patient_id = patient_options[selected_label]

try:
    patient_detail = mcp_server.get_patient(selected_patient_id)
except ValueError:
    st.error("That patient could not be found in the public dataset.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Patient", patient_detail["name"])
col2.metric("Gender", patient_detail.get("gender") or "unknown")
col3.metric("Birth date", patient_detail.get("birth_date") or "unknown")
col4.metric("Synthetic Patient ID", selected_patient_id[:8] + "…")
st.caption(f"Full ID: `{selected_patient_id}` — Fictional Synthea-generated patient.")

# --- patient summary ---------------------------------------------------

st.header("2. Patient summary")
summary = _cached_patient_summary(selected_patient_id)
sc1, sc2, sc3, sc4, sc5 = st.columns(5)
sc1.metric("Allergies", summary["allergy_count"])
sc2.metric("Medications", summary["medication_count"])
sc3.metric("Conditions", summary["condition_count"])
sc4.metric("Observations", summary["observation_count"])
sc5.metric("Encounters", summary["encounter_count"])
st.caption("Counts only — MEVA does not calculate risk, severity, or any clinical interpretation.")

# --- evidence explorer ------------------------------------------------

st.header("3. Evidence explorer")
tabs = st.tabs(["Allergies", "Medications", "Conditions", "Observations", "Encounters"])

with tabs[0]:
    allergies = mcp_server.get_allergies(selected_patient_id)
    if not allergies:
        st.info("No allergies recorded for this patient.")
    else:
        st.dataframe(
            [{"Name": a["name"], "Criticality": a.get("criticality"), "Clinical status": a.get("clinical_status"),
              "Resource ID": a["id"]} for a in allergies],
            use_container_width=True, hide_index=True,
        )

with tabs[1]:
    medications = mcp_server.get_medications(selected_patient_id)
    if not medications:
        st.info("No medications recorded for this patient.")
    else:
        st.dataframe(
            [{"Name": m["name"], "Status": m.get("status"), "Intent": m.get("intent"),
              "Resource ID": m["id"]} for m in medications],
            use_container_width=True, hide_index=True,
        )

with tabs[2]:
    conditions = mcp_server.get_conditions(selected_patient_id)
    if not conditions:
        st.info("No conditions recorded for this patient.")
    else:
        st.dataframe(
            [{"Name": c["name"], "Clinical status": c.get("clinical_status"), "Onset": c.get("onset"),
              "Resource ID": c["id"]} for c in conditions],
            use_container_width=True, hide_index=True,
        )

with tabs[3]:
    observations = mcp_server.get_observations(selected_patient_id, limit=20)
    if not observations:
        st.info("No observations recorded for this patient.")
    else:
        # Presentation-only fix (Stage 8C, docs/observation-audit.md §6): a composite
        # observation (e.g. Blood Pressure) has a null top-level 'value'; the real
        # combined reading lives in 'blood_pressure'. observation_display_value() picks
        # whichever is meaningful for DISPLAY — it does not change MCP or verifier behavior.
        st.dataframe(
            [{"Name": o["name"], "Value": observation_display_value(o), "Resource ID": o["id"]} for o in observations],
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "Composite observations (e.g. Blood Pressure) show their combined reading here "
            "for readability — see docs/playground.md, 'Observation display' for why the "
            "underlying tool data separates this into components."
        )

with tabs[4]:
    encounters = mcp_server.get_encounters(selected_patient_id, limit=20)
    if not encounters:
        st.info("No encounters recorded for this patient.")
    else:
        st.dataframe(
            [{"Type": e["type"], "Status": e["status"], "Start": e.get("start"), "End": e.get("end")} for e in encounters],
            use_container_width=True, hide_index=True,
        )

with st.expander("Developer: normalized JSON for this patient", expanded=False):
    st.json({
        "patient": patient_detail, "allergies": allergies, "medications": medications,
        "conditions": conditions, "observations": observations, "encounters": encounters,
    })

st.divider()

# --- claim builder -------------------------------------------------------

st.header("4. Build a claim to verify")

if "claim_form" not in st.session_state:
    st.session_state.claim_form = {
        "category": "allergy", "assertion": "present", "value": "", "attribute": "", "attribute_value": "",
    }

st.subheader("Try an example")
examples = _cached_ready_made_examples()
example_cols = st.columns(len(examples))
for col, example in zip(example_cols, examples):
    if col.button(example["label"], help=example["description"], use_container_width=True):
        st.session_state.claim_form = {
            "category": example["category"], "assertion": example["assertion"],
            "value": example["value"] or "", "attribute": example["attribute"] or "",
            "attribute_value": example["attribute_value"] or "",
        }
        # Sync the patient selector widget itself (not just the local variable) so the
        # dropdown above visibly reflects the example's patient after rerun.
        st.session_state["patient_selector"] = label_by_patient_id[example["patient_id"]]
        st.session_state["_example_loaded"] = True
        st.rerun()

if st.session_state.pop("_example_loaded", False):
    st.info(f"Example loaded for patient `{selected_patient_id}` — press **Verify claim** below.")

with st.form("claim_builder"):
    category = st.selectbox(
        "Category", options=CLAIM_CATEGORIES, index=CLAIM_CATEGORIES.index(st.session_state.claim_form["category"]),
        help="What kind of record this claim is about.",
    )
    assertion = st.selectbox(
        "Assertion", options=CLAIM_ASSERTIONS, index=CLAIM_ASSERTIONS.index(st.session_state.claim_form["assertion"]),
        help=(
            "present: a named item exists. absent: nothing exists (leave Value blank) or a "
            "named item doesn't exist (fill in Value). value: a specific recorded reading. "
            "attribute: a metadata field of an already-named item. interpretation: a clinical "
            "judgement — MEVA always returns UNVERIFIABLE for these by design."
        ),
    )
    value = st.text_input(
        "Value", value=st.session_state.claim_form["value"],
        help="Required for present/value/attribute claims. Optional for absent claims (blank = category-wide).",
    )
    attribute = attribute_value = ""
    if assertion == "attribute":
        col_a, col_b = st.columns(2)
        attribute = col_a.text_input("Attribute", value=st.session_state.claim_form["attribute"], help="e.g. criticality, clinical_status, status, intent, onset")
        attribute_value = col_b.text_input("Attribute value", value=st.session_state.claim_form["attribute_value"], help="e.g. low, active, resolved")

    submitted = st.form_submit_button("Verify claim", type="primary")

if assertion == "interpretation":
    st.caption(
        "Note: MEVA does not evaluate clinical interpretations — a claim like this will "
        "normally return UNVERIFIABLE. It's allowed here for demonstration."
    )

# --- dynamic, beginner-friendly validation --------------------------------

def _validate_form(category: str, assertion: str, value: str, attribute: str, attribute_value: str) -> str | None:
    if assertion in ("present", "value") and not value.strip():
        return f"'{assertion}' claims need a Value."
    if assertion == "attribute":
        if not value.strip():
            return "Attribute claims need a Value (which item) as well as Attribute and Attribute value."
        if not attribute.strip() or not attribute_value.strip():
            return "Attribute claims need both Attribute and Attribute value filled in."
    return None


# --- verify ----------------------------------------------------------------

if submitted:
    error = _validate_form(category, assertion, value, attribute, attribute_value)
    if error:
        st.error(error)
    else:
        try:
            result = verify_claim(
                selected_patient_id, category, assertion,
                value=value.strip() or None,
                attribute=attribute.strip() or None,
                attribute_value=attribute_value.strip() or None,
            )
        except (ValueError, ValidationError):
            st.error("That combination of fields isn't a valid claim. Check the field help text above and try again.")
        except Exception:
            st.error("MEVA couldn't verify that claim. Please check your inputs and try again.")
        else:
            st.header("5. Result")
            status = result["status"]
            status_row = st.container(border=True)
            status_row.markdown(f"### Status: **{status}**")
            status_row.caption(STATUS_EXPLANATIONS[status])
            status_row.markdown(f"**Claim:** {result['claim']['text']}")
            status_row.markdown(f"**Reason:** {result['reason']}")

            st.subheader("Evidence used")
            if result["evidence"]:
                st.dataframe(
                    [{"Source tool": e["source_tool"], "Evidence value": e["value"], "Resource ID": e["resource_id"]}
                     for e in result["evidence"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption("No supporting evidence was found or applicable for this verdict.")

            with st.expander("Advanced: MedicalClaim JSON", expanded=False):
                st.json(result["claim"])

with st.expander("What do the statuses mean?", expanded=False):
    for status, explanation in STATUS_EXPLANATIONS.items():
        st.markdown(f"**{status}** — {explanation}")

st.divider()

# --- about the benchmark ---------------------------------------------------

st.header("About the benchmark")
st.markdown(
    "**Current public reproducible dataset: MEVA benchmark v0.4** — 53 cases, "
    "21 public synthetic patients (the same patients in this sandbox).\n\n"
    "**v0.4 model comparison results: pending** — no qwen3:4b/llama3.2:3b run has been "
    "performed against v0.4 yet.\n\n"
    "A separate, earlier benchmark (v0.3) has full historical model-comparison results, "
    "but it used a different (now-removed) patient set — see "
    "[`docs/baseline-results-v0.3.md`](docs/baseline-results-v0.3.md), clearly labeled "
    "**historical development baseline**, not a v0.4 result."
)

# --- about MEVA --------------------------------------------------------

st.header("About MEVA")
st.markdown(
    "- [`README.md`](README.md) — project overview\n"
    "- [`docs/benchmarking.md`](docs/benchmarking.md) — benchmark methodology\n"
    "- [`docs/evidence-verification.md`](docs/evidence-verification.md) — the deterministic verifier\n"
    "- [`docs/safety-and-scope.md`](docs/safety-and-scope.md) — what MEVA is and is not\n"
    "- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute"
)

# --- privacy -------------------------------------------------------------

st.header("Privacy")
st.markdown(
    "- All patient data displayed here is **synthetic** (Synthea-generated, entirely fictional).\n"
    "- This sandbox does **not** require you to enter any personal or medical information.\n"
    "- **Please do not paste real patient information into this sandbox.**\n"
    "- Claim text you enter is used only to compute the result shown above — it is not "
    "logged, stored, or sent anywhere. This app makes no external network calls, has no "
    "analytics, tracking, or cookies."
)
