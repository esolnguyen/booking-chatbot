# AI Booking Recommendation MVP

A FastAPI + Streamlit project that recommends flight and hotel combinations for corporate travel, validates policy and factual consistency, and routes low-confidence responses to human review.

## Features

- Corporate trip recommendation pipeline (flights + hotels)
- Deterministic policy checks (tier budgets, preferred vendors, inventory)
- LLM recommendation and verification agents
- Confidence scoring and route selection:
	- `auto_suggest`
	- `suggest_with_caution`
	- `human_review`
- Human-in-the-loop approval workflow for flagged recommendations
- Mock inventory and knowledge base for repeatable testing
- Streamlit chat UI and FastAPI endpoints

## Tech Stack

- Python 3.10+
- FastAPI
- Streamlit
- Pydantic / pydantic-settings
- LangChain + LangGraph (StateGraph orchestration)
- Azure OpenAI

## Harness engineering

The pipeline is built as an AI *harness* — everything around the model that
makes it trustworthy:

- **Context engineering** — retrieval + rerank, with an optional relevance floor
  (`retrieval_min_score`) that drops weak matches so they don't pollute context.
- **Deterministic guardrails** — a composable hard-cap registry
  (`app/validation/hard_caps.py`): policy / price / claim / inventory /
  hallucinated-citation / no-evidence signals force confidence to a ceiling the
  LLM cannot argue past.
- **Agent loop** — a bounded self-repair loop (`app/orchestrator/graph.py`): a
  recoverable defect (a fabricated citation) triggers a re-ask with corrective
  feedback, capped by `max_agent_iterations`; hard fails escalate immediately.
- **Verification & evals** — the offline golden-set routing harness (`evals/`,
  CI-gated) plus optional live RAGAS RAG-quality metrics
  (`python -m evals.run_evals --live --ragas`).
- **Telemetry** — local-first spans, token counts, and USD cost per run
  (`app/telemetry.py`); no third-party SaaS by default (optional OpenTelemetry
  export; LangSmith is an opt-in env flag away).

## Project Structure

```text
app/
	agents/ # Recommendation + verification agents
	mock/ # Mock inventory + knowledge base seed data
	models/ # Request/response domain models
	orchestrator/ # Retrieval, reranking, routing, full pipeline
	validation/ # Policy/fact/response verification logic
	approval_store.py
	config.py
	main.py
chatbot.py # Streamlit chat assistant UI
test_request.py # Quick API smoke test
test/ # Scenario docs and test cases
```

## Prerequisites

- Python 3.10 or newer
- Azure OpenAI resource with:
	- chat deployment
	- embedding deployment

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Configuration

Copy `.env.example` to `.env` and fill in your Azure settings:

```bash
cp .env.example .env
```

Required values:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

Optional runtime settings (already defaulted in code):

- retrieval/agent timeouts
- routing thresholds
- retrieval/rerank top-k

## Run the API

```bash
uvicorn app.main:app --reload
```

Base URL: `http://localhost:8000`

Useful endpoints:

- `GET /health`
- `POST /recommend`
- `GET /approvals/pending`
- `GET /approvals/{approval_id}`
- `POST /approvals/{approval_id}/approve`
- `POST /approvals/{approval_id}/reject`

## Run the Chat UI

```bash
streamlit run chatbot.py
```

The UI includes:

- trip profile controls (tier, destination, dates, preferences)
- verification toggle and confidence threshold slider
- quick scenario buttons (Tokyo, Bangkok, New York)
- escalation flow for human review

## Example API Request

```bash
curl -X POST "http://localhost:8000/recommend" \
	-H "Content-Type: application/json" \
	-d '{
		"traveler": {
			"employee_id": "EMP-001",
			"name": "Alice Johnson",
			"department": "Engineering",
			"org_policy_tier": "standard"
		},
		"origin": "SFO",
		"destination": "Tokyo",
		"departure_date": "2026-04-01",
		"return_date": "2026-04-05",
		"trip_purpose": "business",
		"preferences": ["non_stop", "hotel_gym"]
	}'
```

## Confidence and Routing

The pipeline computes confidence from policy, inventory, evidence quality, freshness, and risk margin, then maps to a route:

- `>= 0.85` -> `auto_suggest`
- `0.60 - 0.84` -> `suggest_with_caution`
- `< 0.60` -> `human_review`

Hard caps are applied when critical checks fail (for example inventory failure or policy violations).

## Human-in-the-Loop Workflow

When route is `suggest_with_caution` or `human_review`:

1. Recommendation is marked `approval_required=true`
2. A pending approval record is created with an `approval_id`
3. Reviewer can approve/reject through approval endpoints

Note: approvals are stored in-memory (`app/approval_store.py`) for MVP use.

## Quick Testing

Unit tests for the deterministic guardrails (offline, no Azure cost):

```bash
python -m pytest -q
```

### Routing eval harness

`evals/` adds a golden-set harness that runs the **real** pipeline (router,
policy/fact checkers, hard caps, freshness) with the LLM agents and vector store
faked, to measure routing precision/recall and threshold calibration:

```bash
python -m evals.run_evals          # offline, deterministic, zero Azure spend
python -m evals.run_evals --live   # real Azure OpenAI; measures grounding rate
```

It gates CI on the deterministic hard-cap scenarios and reports calibration
divergences on the soft ones. See `evals/README.md`.

Run the API smoke script:

```bash
python test_request.py
```

Reference docs:

- `test/TEST_CASES.md` — confidence/routing test cases. **Note:** the inventory
  cheat sheet in this file is stale (it lists a New York / JFK inventory that no
  longer exists in `seed_data.py`, which now uses Sydney). The eval golden set is
  built from the live seed data and is the source of truth.
- `test/test_scenarios.md`
- `test/sample_questions.md`

## Notes and Limitations

- Data sources are mocked (inventory + knowledge base)
- Approval store is in-memory and resets on restart
- This project is an MVP and not production-hardened

## Troubleshooting

- `401` or auth errors: verify Azure OpenAI key/endpoint/deployment names in `.env`
- Empty or low-quality recommendations: confirm embedding + chat deployments are valid
- API does not start: ensure dependencies are installed and the virtual environment is active
# booking_chatbot
