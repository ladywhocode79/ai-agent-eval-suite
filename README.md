# AI Agent Eval Suite

A CI-integrated testing harness for LLM agents, built on [pytest](https://pytest.org), [deepeval](https://github.com/confident-ai/deepeval) and the Anthropic Claude API. It tests a safety-critical **meal-planner agent** (allergen-aware recipe recommendations) and, before trusting any LLM judge, checks that judge against human labels.

> The simple Q&A framework (relevancy, faithfulness, deterministic metrics, local Ollama judge) lives in the companion repo [llm-eval-framework](https://github.com/ladywhocode79/llm-eval-framework). This repo holds the meal-planner scenarios, the two-layer architecture, judge calibration, model benchmarking and the CI pipeline. The 6-week plan is in [Learning_plan.md](Learning_plan.md).

## Two-layer testing

Cheap deterministic checks run first; paid LLM judging only happens if they pass.

```
  Scenario (datasets/golden_set.json)
            │
            ▼
  ┌───────────────────────────────────┐
  │ LAYER A — Deterministic           │
  │ Pydantic tool-call schema check   │
  └─────────┬───────────────┬─────────┘
         pass              fail ──► stop (no LLM cost)
            ▼
  ┌───────────────────────────────────┐
  │ LAYER B — LLM-as-judge (deepeval) │
  │ Faithfulness                      │
  │ allergen_safety_metric (GEval)    │  only if an allergen is declared
  │ AnswerRelevancy                   │  skipped if expects_refusal
  └───────────────────────────────────┘
```

Before any of this is trusted in CI, the judge itself is calibrated against a human-annotated gold set (**Cohen's κ ≥ 0.80**).

## Repository layout

```
ai-agent-eval-suite/
├── .github/workflows/llm_evals_ci.yaml   # CI: calibration gate → parallel scenario evals → reports
├── datasets/
│   ├── golden_set.json                   # Meal-planner scenarios (tool calls + expected output)
│   └── human_annotated_sets.json         # Human-labelled gold set for judge calibration
├── frameworks/evals/
│   ├── judge_factory.py                  # Resolves the judge at runtime (ollama / gemini / anthropic)
│   └── local_judge.py                    # Ollama judge wrapper
├── tests/
│   ├── test_evals.py                     # Layer A + Layer B scenario runner
│   ├── test_judge_calibration.py         # Judge vs. human agreement (Cohen's κ)
│   └── test_model_benchmark.py           # Haiku 4.5 vs Sonnet 5.5 judge: κ, latency, cost
├── scripts/check_setup.py                # Pre-flight setup checker
├── docs/                                 # CI/CD page, case study (challenges & learnings), glossary
├── reports/                              # Generated HTML / JUnit / benchmark reports
├── pytest.ini
├── requirements.txt
└── Learning_plan.md
```

## Setup

```bash
git clone https://github.com/ladywhocode79/ai-agent-eval-suite.git
cd ai-agent-eval-suite

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then set ANTHROPIC_API_KEY (and optionally judge settings)
python scripts/check_setup.py     # verify the setup
```

### Judge selection

The judge is resolved at runtime by `frameworks/evals/judge_factory.py`. `EVAL_JUDGE_BACKEND` (falls back to `JUDGE_BACKEND`) controls it:

| Value | Behavior |
|-------|----------|
| `auto` (default) | Prefer local Ollama if running and the model is pulled; else `GEMINI_API_KEY`, then `ANTHROPIC_API_KEY` |
| `ollama` | Force local Ollama (`OLLAMA_MODEL`) |
| `gemini` | Force Gemini (`GEMINI_API_KEY`) |
| `anthropic` | Force Claude (`ANTHROPIC_API_KEY`) |

Prefer local for simple checks, but verify it against your rubric — a local llama3.2 judge hallucinated facts about the retrieval context on the allergen rubric ([case study 6](docs/case-study/06-model-agnostic-judge.md)), so this project pins `EVAL_JUDGE_BACKEND=anthropic`.

## Running tests

```bash
pytest -m calibration -s                     # Option A: judge calibration gate (κ ≥ 0.80)
pytest -m evals -n auto                      # Option B: Layer A + B scenarios in parallel
pytest -m calibration && pytest -m evals -n auto   # Option C: chained, same order as CI
pytest -m benchmark -v -s                    # Option D: judge model benchmark (live calls to two models)

# Single scenario (parametrized by scenario_id)
pytest "tests/test_evals.py::test_meal_planner_scenario[MP_VAL_001]" -v
```

### Sequential execution (no parallelism)

`pytest.ini` sets `-n auto` (pytest-xdist). Pass `-n 0` to disable workers and run every test sequentially on the main thread:

```bash
# Option 1: calibration gate only
pytest tests/test_judge_calibration.py -m calibration -n 0 -s

# Option 2: scenario evaluation suite only
pytest tests/test_evals.py -m evals -n 0 -s

# Option 3: chained — scenarios run only if calibration passes (κ ≥ 0.80)
pytest tests/test_judge_calibration.py -m calibration -n 0 -s && pytest tests/test_evals.py -m evals -n 0 -s
```

Reports are written to `reports/report.html` and `reports/report.xml` on every run; the benchmark also writes `reports/model_benchmark.md` and `.json`.

## Judge calibration

`tests/test_judge_calibration.py` scores `datasets/human_annotated_sets.json` with the **same judge, rubric and metrics as `test_evals.py`** and asserts Cohen's κ ≥ 0.80 against the human labels. A case is judge-pass only if **all** its metrics pass; `expects_refusal: true` cases skip AnswerRelevancy. On failure, the message lists the disagreeing `scenario_id`s — read each case's `reasoning` to decide whether the judge or the label is wrong. With 10 cases, one disagreement gives κ = 0.80 and two give 0.60.

Gold-set entry format:
```json
{
  "scenario_id": "CALIB_011",
  "persona": "Short description of the user",
  "input": "User's request",
  "actual_output": "The agent response to judge",
  "retrieved_context": ["Recipe_...: ..."],
  "human_label": 1,
  "expects_refusal": false,
  "reasoning": "Why a human labelled it 1 (acceptable) or 0 (unacceptable)"
}
```
Details: [docs/case-study/07-judge-calibration.md](docs/case-study/07-judge-calibration.md).

## Adding golden-set scenarios

Append to `datasets/golden_set.json`:
```json
{
  "scenario_id": "MP_XXX_003",
  "persona": "Short description of the user",
  "input": "User's request to the meal planner",
  "retrieved_context": ["Recipe_301: ...", "Recipe_302: ..."],
  "expected_tool_call": { "name": "fetch_recipes", "args": { "meal_type": "dinner" } },
  "actual_output": "The agent's actual response",
  "expected_output": "The ideal response",
  "expects_refusal": false
}
```
The allergen-safety metric attaches only when `expected_tool_call.args.exclude_allergens` is set.

## Judge model benchmark

Compares `claude-haiku-4-5-20251001` and `claude-sonnet-5-5` on the same calibration set and rubric (κ, p50/p95 latency, estimated cost). Notes: cost uses fixed token estimates and an **assumed** Sonnet 5.5 price; Sonnet 5.5 rejects `temperature`, so it is not pinned to 0 and results can vary; only the safety metric is scored, so the off-topic case `CALIB_007` is likely a miss. First observed run: Haiku 4.5 κ = 0.60 (failed the gate); Sonnet numbers weren't captured. Details: [docs/case-study/08-model-benchmark.md](docs/case-study/08-model-benchmark.md).

## CI/CD (GitHub Actions)

`.github/workflows/llm_evals_ci.yaml` runs on pull requests to `main`/`master` and pushes to `main`:

1. **Judge calibration gate** — `pytest -m calibration -s`; fails if κ < 0.80.
2. **Scenario evals** (only if stage 1 passes) — `pytest -m evals -n auto`.
3. **Publish** — uploads the `llm-eval-reports` artifact (14 days) and writes a PR summary.

Add `ANTHROPIC_API_KEY` under **Settings → Secrets and variables → Actions**. The runner has no Ollama, so the judge resolves to Claude; fork PRs don't get secrets. Benchmarks are not run in CI. Full details: [docs/ci-cd-pipeline.md](docs/ci-cd-pipeline.md).

## Documentation

- [CI/CD pipeline](docs/ci-cd-pipeline.md)
- [Case study index](docs/case-study/README.md) — eight challenges and their learnings, plus [consolidated takeaways](docs/case-study/09-takeaways.md)
- [Glossary](docs/glossary.md)
- Fundamentals, metrics and the local Ollama judge: [llm-eval-framework docs](https://github.com/ladywhocode79/llm-eval-framework/tree/main/docs)

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No judge model available` | No Ollama and no API key | Set `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` in `.env`, or run Ollama |
| `temperature is deprecated for this model` (400) | Newer Claude model rejects `temperature` | Handled by `ClaudeLLM` (retries without it) |
| CI Stage 2 "no tests collected" (code 5) | `-m` marker matches no test | Tests must carry the `evals` marker |
| Calibration κ < 0.80 | Judge disagrees with human labels | Check the listed `scenario_id`s and `reasoning` |
| Anything unclear | — | `python scripts/check_setup.py` |
