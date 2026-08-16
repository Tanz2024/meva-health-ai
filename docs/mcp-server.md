# MEVA MCP Server

## What is MCP?

MCP (Model Context Protocol) is a standard way for an AI assistant (an
"MCP client", like Claude) to call tools exposed by a program (an "MCP
server") over a simple protocol. The AI doesn't need custom code for
every tool — it just asks the server "what tools do you have?" and then
calls them, the same way it would call any other tool.

## Why MEVA uses MCP

MEVA's job is to let an AI agent look up medical evidence in a
controlled, read-only way. Instead of giving an AI raw file access,
MEVA exposes a small, fixed set of safe lookup tools. The AI can only
do what MEVA explicitly allows — nothing more.

## What is an MCP server?

A small Python program that:
1. Registers a list of tools (plain Python functions).
2. Listens for requests from an MCP client (over stdio, in this stage).
3. Runs the matching function and sends back the result.

MEVA's server lives at `src/meva/mcp/server.py`.

## What is an MCP tool?

A single Python function, decorated with `@mcp.tool()`, with type hints
and a docstring. MCP reads the type hints and docstring automatically to
tell the AI what the tool does and what arguments it needs — you don't
write any separate schema by hand.

## Architecture

```text
MCP Client
    ↓
MEVA MCP tools        (src/meva/mcp/server.py)
    ↓
MEVA FHIR layer        (src/meva/fhir/*)
    ↓
Synthetic Synthea FHIR  (data/synthetic/synthea/*.json)
```

The MCP layer contains **no FHIR parsing logic of its own** — it only
calls the functions already built and tested in Stage 2/3
(`meva.fhir`), plus one small helper (`meva.mcp.registry`) that maps a
`patient_id` to the right synthetic bundle file.

## MEVA's tools

| Tool | Input | Returns |
|---|---|---|
| `list_patients` | — | ID, name, and source file for every synthetic patient |
| `get_patient` | `patient_id` | ID, name, gender, birth date |
| `get_allergies` | `patient_id` | Recorded allergies (name, criticality, status) |
| `get_medications` | `patient_id` | Recorded medication requests |
| `get_conditions` | `patient_id` | Recorded conditions/diagnoses |
| `get_observations` | `patient_id`, `limit` (default 20, max 100) | Recorded vitals/labs |
| `get_encounters` | `patient_id`, `limit` (default 20, max 100) | Recorded visits |

All tools are **read-only retrieval tools**. They report what's recorded
in the synthetic FHIR data — they never diagnose, recommend treatment,
or suggest medications. An empty list means "nothing recorded", not an
error.

## Starting the development server

```bash
source .venv/bin/activate
mcp dev src/meva/mcp/server.py
```

This starts MEVA's MCP server and opens **MCP Inspector**, a web UI for
testing MCP servers by hand (it uses `npx`, which must be installed —
check with `npx --version`).

## Testing with MCP Inspector

1. Run the command above; Inspector opens in your browser.
2. Click **List Tools** — you should see all 7 tools listed above.
3. Try `list_patients` with no arguments — see the 3 synthetic patients.
4. Copy a `patient_id` from that result and try `get_patient`,
   `get_allergies`, `get_conditions`, etc. with it.
5. Try an ID that doesn't exist (e.g. `"not-a-real-id"`) — you should
   get a clear error, not a crash or fabricated data.
6. Try `get_observations` with `limit: 500` — you should get an error
   saying the limit must be between 1 and 100.

## Safety limitations (by design)

- **No arbitrary file access.** Tools only ever accept a `patient_id`
  string, never a filename or path. The server looks that ID up against
  bundles it already found inside `data/synthetic/synthea/` — a string
  like `"../../etc/passwd"` or `"patient-01.json"` simply won't match
  any known patient ID, so it's rejected the same way an unknown ID is.
- **Bounded output.** `limit` on `get_observations` and `get_encounters`
  is capped at 100, so a caller can't force unlimited output.
- **No stack traces or paths leaked.** Errors are plain, short messages
  (e.g. "No synthetic patient found with ID '...'") — never a Python
  traceback, absolute file path, or environment detail.
- **No medical interpretation.** These tools return recorded facts only.
  They do not diagnose, prescribe, or recommend treatment.
- **Synthetic data only.** Every patient is Synthea-generated and
  entirely fictional — see `docs/synthetic-data.md`.
