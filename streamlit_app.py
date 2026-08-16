"""MEVA Browser Sandbox — a Streamlit UI over MEVA's real, deterministic
evidence verifier and the public v0.4 synthetic dataset.

This file is intentionally thin: every piece of actual logic (listing
patients, describing them, verifying a claim, picking a display value for a
composite observation, translating a plain-English Guided Mode choice into
a MedicalClaim) lives in meva.playground.service and meva.playground.guided
— the same modules the Stage 8B CLI (examples/playground.py) uses. This
file only builds the UI and calls those services — it implements no
verification rules of its own, in either Guided or Advanced Mode.

No AI model inference happens anywhere in this app (no Ollama, no
qwen3:4b/llama3.2:3b, no claim extraction, no chat) and it makes no
outbound network calls of any kind — everything needed is packaged with
the repository. See docs/playground.md, "Browser Sandbox" for the full
picture, and docs/playground.md, "Guided Mode" for how plain-English
choices map onto MedicalClaim fields.

Run locally (after `pip install -e ".[playground]"`):
    streamlit run streamlit_app.py
"""

import streamlit as st
from pydantic import ValidationError

from meva.playground import (
    CATEGORY_VALUE_HINTS,
    GUIDED_CATEGORIES,
    GUIDED_CATEGORY_LABELS,
    GUIDED_CUSTOM_LABELS,
    GUIDED_RESULT_EXPLANATIONS,
    build_ready_made_examples,
    describe_patient,
    format_datetime_display,
    guided_custom_claim,
    guided_options,
    list_patients,
    observation_display_value,
    suggested_values,
    verify_claim,
)
from meva.mcp import server as mcp_server
from meva.verification.models import CLAIM_ASSERTIONS, CLAIM_CATEGORIES

GITHUB_URL = "https://github.com/Tanz2024/meva-health-ai"

# (icon, alert-box function) per status — icon+text together, never color alone.
STATUS_DISPLAY = {
    "SUPPORTED": ("✅", st.success),
    "CONTRADICTED": ("❌", st.error),
    "UNSUPPORTED": ("➖", st.warning),
    "UNVERIFIABLE": ("❓", st.info),
}

# Advanced Mode wording — technical/precise.
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


@st.cache_data(show_spinner=False)
def _cached_guided_options(patient_id: str, category: str) -> list[dict]:
    return guided_options(patient_id, category)


# --- shared result rendering (used by both Guided and Advanced Mode) -------

def render_result(result: dict, *, guided: bool) -> None:
    status = result["status"]
    icon, alert_fn = STATUS_DISPLAY[status]
    explanations = GUIDED_RESULT_EXPLANATIONS if guided else STATUS_EXPLANATIONS

    status_row = st.container(border=True)
    with status_row:
        alert_fn(f"{icon} **{status}**")
        st.caption(explanations[status])
        if guided:
            st.markdown(f"**You checked:** {result['claim']['text']}")
        else:
            st.markdown(f"**Claim:** {result['claim']['text']}")
            st.markdown(f"**Reason:** {result['reason']}")

    if guided:
        if result["evidence"]:
            st.markdown("**Evidence found**")
            for evidence in result["evidence"]:
                st.markdown(f"- {evidence['value']}")
        else:
            st.caption("No matching evidence was found for this claim.")

        with st.expander("Show technical details", expanded=False):
            st.markdown(f"**Reason:** {result['reason']}")
            if result["evidence"]:
                st.dataframe(
                    [{"Source tool": e["source_tool"], "Evidence value": e["value"], "Resource ID": e["resource_id"]}
                     for e in result["evidence"]],
                    width="stretch", hide_index=True,
                )
            st.json(result["claim"])
    else:
        st.subheader("Evidence used")
        if result["evidence"]:
            st.dataframe(
                [{"Source tool": e["source_tool"], "Evidence value": e["value"], "Resource ID": e["resource_id"]}
                 for e in result["evidence"]],
                width="stretch", hide_index=True,
            )
        else:
            st.caption("No supporting evidence was found or applicable for this verdict.")

        with st.expander("Advanced: MedicalClaim JSON", expanded=False):
            st.json(result["claim"])


def _validate_form(category: str, assertion: str, value: str, attribute: str, attribute_value: str) -> str | None:
    if assertion in ("present", "value") and not value.strip():
        return f"'{assertion}' claims need a Value."
    if assertion == "attribute":
        if not value.strip():
            return "Attribute claims need a Value (which item) as well as Attribute and Attribute value."
        if not attribute.strip() or not attribute_value.strip():
            return "Attribute claims need both Attribute and Attribute value filled in."
    return None


# --- header ------------------------------------------------------------

header_col, github_col = st.columns([5, 1])
with header_col:
    st.title("MEVA")
    st.subheader("Medical Evidence Verification Agent")
    st.caption("MEVA checks whether a claim matches a fictional patient's recorded medical evidence.")
with github_col:
    st.link_button("⭐ View on GitHub", GITHUB_URL, width="stretch")

st.warning(
    "**Synthetic data only. Not medical advice. Not for diagnosis or treatment.** "
    "No AI model runs in this public sandbox — every patient here is fictional "
    "(Synthea-generated). See the Privacy section below.",
    icon="⚠️",
)

with st.expander("What is MEVA?", expanded=False):
    st.markdown(
        "MEVA is an open-source research tool that checks whether AI-style claims "
        "are supported by recorded evidence in synthetic FHIR patient data.\n\n"
        "**It is not a chatbot and does not provide medical advice.**"
    )

with st.expander("Why would I use this?", expanded=False):
    st.markdown(
        "Students and newcomers can use this sandbox to learn:\n\n"
        "- how structured health records (FHIR) work\n"
        "- how AI-style claims can disagree with the source data\n"
        "- what \"evidence grounding\" means\n"
        "- why independent verification matters in AI systems"
    )

st.divider()

# --- experience mode ---------------------------------------------------

st.session_state.setdefault("experience_mode", "Guided")
mode = st.radio(
    "Experience", options=["Guided", "Advanced"], key="experience_mode", horizontal=True,
    help="Guided: plain-English walkthrough for students/newcomers. Advanced: the full technical claim builder for developers and researchers.",
)
if mode == "Advanced":
    st.caption("Advanced Mode is intended for developers, researchers, and contributors.")

st.divider()

# --- patient selector (shared by both modes) -------------------------------

st.header("1. Choose a fictional patient")

patients = _cached_patient_list()
# Names are unique across all 21 public v0.4 patients, so the dropdown can show
# a plain name instead of a raw UUID — friendlier for Guided Mode visitors.
# The full technical ID still appears in the caption below and in Advanced Mode.
patient_options = {p["name"]: p["patient_id"] for p in patients}
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
    help="All patients are fictional, Synthea-generated data — search by name.",
)
selected_patient_id = patient_options[selected_label]

try:
    patient_detail = mcp_server.get_patient(selected_patient_id)
except ValueError:
    st.error("That patient could not be found in the public dataset.")
    st.stop()

col1, col2 = st.columns(2)
col1.metric("Gender", patient_detail.get("gender") or "unknown")
col2.metric("Birth date", patient_detail.get("birth_date") or "unknown")
st.caption(f"Fictional Synthea-generated patient. Technical ID: `{selected_patient_id}`")

st.divider()

# =============================================================================
# GUIDED MODE
# =============================================================================

if mode == "Guided":
    st.header("2. Choose what you want to check")

    guided_category_options = [label for _, label in GUIDED_CATEGORIES]
    guided_label_to_category = {label: cat for cat, label in GUIDED_CATEGORIES}

    if "guided_category_select" not in st.session_state:
        st.session_state["guided_category_select"] = guided_category_options[0]

    # st.radio (stacked on narrow screens) instead of a row of buttons, so this
    # stays usable on a phone (Stage 8G, "Mobile / small screen").
    guided_category_label = st.radio(
        "What type of information do you want to check?",
        options=guided_category_options, key="guided_category_select",
    )
    guided_category = guided_label_to_category[guided_category_label]

    st.header("3. Choose a claim")

    options = _cached_guided_options(selected_patient_id, guided_category)
    option_labels = [o["label"] for o in options]

    chosen_option = None
    if option_labels:
        st.caption("Try one:")
        for option in options:
            if st.button(option["label"], key=f"guided_opt_{guided_category}_{option['label']}", width="stretch"):
                st.session_state["guided_chosen"] = option
                st.session_state["guided_custom_value"] = ""
                st.rerun()

    custom_label = GUIDED_CUSTOM_LABELS.get(guided_category)
    custom_value = ""
    if custom_label:
        custom_value = st.text_input(
            custom_label, key="guided_custom_value",
            placeholder=CATEGORY_VALUE_HINTS.get(guided_category, ""),
            help="Type your own value — MEVA checks it the same way as the suggestions above.",
        )

    chosen = st.session_state.get("guided_chosen")
    active_claim = None
    if custom_value.strip():
        active_claim = guided_custom_claim(guided_category, custom_value.strip())
    elif chosen:
        active_claim = chosen

    if active_claim:
        st.info(f"Ready to check: **{active_claim['label']}**")

    st.header("4. Check against the record")
    check_clicked = st.button("Check with MEVA", type="primary", disabled=active_claim is None)

    if check_clicked and active_claim:
        try:
            result = verify_claim(
                selected_patient_id, guided_category, active_claim["assertion"],
                value=active_claim["value"],
            )
        except (ValueError, ValidationError):
            st.error("That claim couldn't be checked. Try one of the suggestions above, or a different value.")
        except Exception:
            st.error("MEVA couldn't check that claim. Please try again.")
        else:
            st.header("5. Result")
            render_result(result, guided=True)

    with st.expander("What do the results mean?", expanded=False):
        for status, explanation in GUIDED_RESULT_EXPLANATIONS.items():
            st.markdown(f"**{status}** — {explanation}")

# =============================================================================
# ADVANCED MODE
# =============================================================================

else:
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
                width="stretch", hide_index=True,
            )

    with tabs[1]:
        medications = mcp_server.get_medications(selected_patient_id)
        if not medications:
            st.info("No medications recorded for this patient.")
        else:
            st.dataframe(
                [{"Name": m["name"], "Status": m.get("status"), "Intent": m.get("intent"),
                  "Resource ID": m["id"]} for m in medications],
                width="stretch", hide_index=True,
            )

    with tabs[2]:
        conditions = mcp_server.get_conditions(selected_patient_id)
        if not conditions:
            st.info("No conditions recorded for this patient.")
        else:
            st.dataframe(
                [{"Name": c["name"], "Clinical status": c.get("clinical_status"), "Onset": c.get("onset"),
                  "Resource ID": c["id"]} for c in conditions],
                width="stretch", hide_index=True,
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
                width="stretch", hide_index=True,
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
            # Presentation-only fix: each encounter's raw timestamp carries whatever UTC
            # offset Synthea generated for it (varies record to record) — normalized to
            # UTC here for a consistent table; get_encounters() itself is untouched.
            st.dataframe(
                [{"Type": e["type"], "Status": e["status"],
                  "Start": format_datetime_display(e.get("start")),
                  "End": format_datetime_display(e.get("end"))} for e in encounters],
                width="stretch", hide_index=True,
            )
            st.caption("Times normalized to UTC for consistent display.")

    with st.expander("Developer: normalized JSON for this patient", expanded=False):
        st.json({
            "patient": patient_detail, "allergies": allergies, "medications": medications,
            "conditions": conditions, "observations": observations, "encounters": encounters,
        })

    st.divider()

    # --- claim builder -------------------------------------------------------

    st.header("4. Build a claim to verify")
    st.caption("Not sure what to type? Try an example below, or use a suggested value once you pick a category.")

    if "claim_form" not in st.session_state:
        st.session_state.claim_form = {
            "category": "allergy", "assertion": "present", "value": "", "attribute": "", "attribute_value": "",
        }

    st.subheader("Try an example")
    examples = _cached_ready_made_examples()
    example_cols = st.columns(len(examples))
    for col, example in zip(example_cols, examples):
        if col.button(example["label"], help=example["description"], width="stretch"):
            st.session_state.claim_form = {
                "category": example["category"], "assertion": example["assertion"],
                "value": example["value"] or "", "attribute": example["attribute"] or "",
                "attribute_value": example["attribute_value"] or "",
            }
            # Sync the patient selector widget itself (not just the local variable) so the
            # dropdown above visibly reflects the example's patient after rerun.
            st.session_state["patient_selector"] = label_by_patient_id[example["patient_id"]]
            st.session_state["claim_category_select"] = example["category"]
            st.session_state["_example_loaded"] = True
            st.rerun()

    if st.session_state.pop("_example_loaded", False):
        st.info(f"Example loaded for patient `{selected_patient_id}` — press **Verify claim** below.")

    # Category lives OUTSIDE the form (not inside st.form) so suggestions below react
    # immediately as the visitor changes it, instead of only after submitting.
    if "claim_category_select" not in st.session_state:
        st.session_state["claim_category_select"] = st.session_state.claim_form["category"]

    category = st.selectbox(
        "Category", options=CLAIM_CATEGORIES, key="claim_category_select",
        help="What kind of record this claim is about.",
    )

    st.caption(f"Value format for **{category}**: {CATEGORY_VALUE_HINTS.get(category, 'a value matching this record type')}")

    suggestions = suggested_values(selected_patient_id, category)
    if suggestions:
        st.caption(f"Suggested values from **{patient_detail['name']}**'s own record (you may still type anything else):")
        suggestion_cols = st.columns(len(suggestions))
        for col, suggestion in zip(suggestion_cols, suggestions):
            if col.button(suggestion, key=f"suggest_{category}_{suggestion}", width="stretch"):
                st.session_state.claim_form["value"] = suggestion
                st.session_state["claim_value_input"] = suggestion
                st.rerun()

    with st.form("claim_builder"):
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
            "Value", value=st.session_state.claim_form["value"], key="claim_value_input",
            placeholder=CATEGORY_VALUE_HINTS.get(category, ""),
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
                render_result(result, guided=False)

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

# --- want to contribute? -------------------------------------------------

st.header("Want to contribute?")
st.markdown(
    f"MEVA is open source. See "
    f"[open issues / good first issues]({GITHUB_URL}/issues) and "
    "[`CONTRIBUTING.md`](CONTRIBUTING.md) for a step-by-step guide, or "
    "[`docs/contributor-issues.md`](docs/contributor-issues.md) for a list "
    "of concretely scoped starter tasks."
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
