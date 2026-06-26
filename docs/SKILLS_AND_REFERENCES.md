# Skills & Reference Index

This document captures the key skills covered by this project and maps each skill
to the relevant reference documents available in the shared template repository.
It lives in git so it is always accessible without needing to browse the template
directory directly.

**Template base path** (not in git — local server only):
```
/export/ws/cxo-bsrv05-wrksp3/balakrin/ai-code-assistant/r6/ai-code-assistant-template/
```

---

## How to Use This Document

Each skill section below lists:
- What you should be able to do after studying it.
- The exact file path(s) in the template directory to read.

When Copilot or a reviewer refers to "check the reference docs", this is the index to use.

---

## 1. Project Definition & Scope

**What you learn:**
- The full problem statement, educational goals, and evaluation criteria for this project.
- The 6-8 week delivery plan, team role split, and milestone checkpoints.
- What is in scope (MVP agents, Python only, Ollama/Gemini) vs. out of scope.
- Realistic expectations: 50-60% coverage acceptable, bugs are learning opportunities.

**Reference documents:**
```
docs/AI_CodeDevelopment_ProblemDefinition.md
docs/AI_Driven_Development_Automation_PRD_v1.0.pdf
```

**Key sections to know:**
- §7 Simplified Implementation Plan (week-by-week breakdown)
- §9 Evaluation Criteria (40% functionality, 25% code quality, 20% AI integration, 15% docs)
- §10 Success Metrics (quantitative targets per agent)
- §13 Getting Started (quick-start commands)
- Appendix A: Sample prompts for Coder and Tester agents
- Appendix B: Configuration examples (workflow_config.yaml)

---

## 2. User Stories & Sprint Planning

**What you learn:**
- All 40 user stories (US-001 to US-040) with acceptance criteria, story points, and priorities.
- Which stories belong to which sprint and which agent/component.
- How to read and write user stories (As a / I want / So that / Acceptance Criteria).
- Sprint ceremony structure (standup, planning, review, retrospective).

**Reference document:**
```
docs/planning/User_Stories_Sprint_Plan.md
```

**Story map by sprint:**

| Sprint | Stories | Focus |
|--------|---------|-------|
| Sprint 1 (Weeks 1-2) | US-001 to US-010 | LLM layer, workflow, infrastructure |
| Sprint 2 (Weeks 3-4) | US-011 to US-024 | Coder agent, Tester agent, integration |
| Sprint 3 (Weeks 5-6) | US-025 to US-040 | Reviewer, Validator, CI/CD, metrics |

**Critical-priority stories to always know:**
- US-001 LLM abstraction layer
- US-004 Workflow state machine
- US-006 CLI
- US-011 Prompt engineering for code generation
- US-012 Code generation from requirements
- US-017 Test case design strategy
- US-018 Automated test generation (pytest)
- US-025 Code review prompt engineering
- US-031 Pre-merge checklist validation
- US-036 Complete workflow integration

---

## 3. Technical Architecture & State Machine

**What you learn:**
- How all components fit together: CLI → Orchestrator → Agents → LLM → Tools.
- The exact state transition model: INIT → CODE → TEST → REVIEW → VALIDATE → COMPLETE.
- When automatic transitions fire vs. when human checkpoints are required.
- Per-agent technical requirements, complexity ratings, and data contracts.
- Feedback loop mechanics: how `FeedbackItem` flows from human/agent back to Coder.

**Reference document:**
```
docs/Technical_Implementation_Guide.md
```

**Key sections:**
- §1 State Transition Model (full diagram with PASS/FAIL branches and rollback paths)
- §3 Coder Agent technical requirements
- §4 Tester Agent technical requirements
- §5 Reviewer Agent technical requirements
- §6 Validator Agent technical requirements
- §7 LLM integration patterns
- §8 Complexity assessment per story

---

## 4. LLM API Abstraction Layer (US-001)

**What you learn:**
- How to build a provider-agnostic LLM client (`BaseLLMClient` ABC).
- OpenAI-compatible API format that works across Gemini, Groq, Claude, Ollama.
- `generate()`, `chat()`, `is_available()`, `get_provider_info()` interface contract.
- Rate limit handling (`RateLimitError`), exponential backoff, retry logic.
- Cost tracking via token counting per provider.
- How to switch providers via config without code changes.

**Reference documents:**
```
docs/guides/LLM_API_GUIDE.md          ← Full implementation guide (US-001)
docs/guides/LLM_VISUAL_OVERVIEW.md    ← Architecture diagrams
docs/guides/US001_SUMMARY.md          ← Acceptance criteria checklist & demo script
src/core/llm_client.py                ← Reference implementation
src/core/config.yaml                  ← Multi-provider config example
example_usage_multimodal.py           ← Working code examples
```

---

## 5. LLM Provider Setup & Free Tier Usage

**What you learn:**
- How to get free API keys for each provider (no credit card needed).
- Rate limits, response speeds, and quality trade-offs per provider.
- When to use which provider: Groq (speed), Gemini (free tier volume), Claude (quality), Ollama (offline/unlimited).
- How to set environment variables for API key management.
- Cost analysis: how to run the entire 6-week project for $0.

**Reference documents:**
```
docs/guides/QUICKSTART_LLM.md    ← 5-minute setup for each provider
docs/guides/GROQ_GUIDE.md        ← Groq free tier (14,400 req/day, llama-3.3-70b)
docs/guides/CLAUDE_GUIDE.md      ← Claude free credit ($5, ~250 tasks)
```

**Quick provider comparison:**

| Provider | Free Limit | Speed | Quality | Offline |
|----------|-----------|-------|---------|---------|
| Groq | 14,400 req/day | ⚡ Ultra-fast (500 tok/s) | High | No |
| Gemini | 1,500 req/day | Fast (2-5s) | High | No |
| Claude | ~$5 credit | Fast (2-5s) | Highest | No |
| Ollama | Unlimited | Slow (10-30s) | Good | ✅ Yes |

**Environment variable names:**
```bash
export GEMINI_API_KEY='...'
export GROQ_API_KEY='...'
export ANTHROPIC_API_KEY='...'
# Ollama: no key needed, run: ollama serve
```

---

## 6. Prompt Engineering

**What you learn:**
- How to structure system prompts vs. user prompts.
- Few-shot prompting: giving the LLM examples to anchor output format.
- Constraints in prompts: type hints, docstrings, PEP 8, max complexity.
- Structured output: using JSON schema to get machine-parseable responses.
- Iterative refinement: passing feedback back into the prompt on retry.
- Why temperature 0.2-0.3 works better for code generation than higher values.

**Reference documents:**
```
docs/planning/User_Stories_Sprint_Plan.md    ← US-011, US-017, US-025 prompt templates
docs/AI_CodeDevelopment_ProblemDefinition.md ← Appendix A: sample Coder + Tester prompts
prompt_templates.py                          ← Working template examples
src/agents/coder_agent.py                    ← Reference Coder Agent prompts
src/agents/tester_agent.py                   ← Reference Tester Agent prompts
```

**Core prompt structure pattern:**
```
[System] Role + constraints + output format rules
[User]   Requirements + existing code context + unresolved feedback items
```

---

## 7. Testing Skills (pytest & coverage)

**What you learn:**
- How to write `pytest` tests: fixtures, parametrize, assertions.
- Normal / edge / error case strategy for test coverage.
- Running `pytest --cov` and parsing coverage reports.
- What "line coverage" vs. "branch coverage" means.
- Mocking external dependencies with `unittest.mock` / `pytest-mock`.
- Target: ≥80% coverage of the framework's own code.

**Reference documents:**
```
docs/planning/User_Stories_Sprint_Plan.md    ← US-017 to US-022 acceptance criteria
docs/AI_CodeDevelopment_ProblemDefinition.md ← §10 Success Metrics table
tests/                                       ← Student test suite (in this repo)
```

**Run tests:**
```bash
pytest tests/ --cov=src/orchestrator --cov-report=term-missing
```

---

## 8. Code Quality & Static Analysis

**What you learn:**
- `pylint` for style, naming, complexity scoring (target score ≥ 8.0/10).
- `flake8` for PEP 8 line-level violations.
- `bandit` for security vulnerability scanning (SQL injection, hardcoded secrets).
- Cyclomatic complexity: what it means and the threshold (≤ 10 per function).
- Code smells: long functions (>50 lines), god classes (>300 lines), magic numbers, duplication.

**Reference documents:**
```
docs/planning/User_Stories_Sprint_Plan.md    ← US-013, US-027, US-029 acceptance criteria
docs/Technical_Implementation_Guide.md       ← §5 Reviewer Agent requirements
```

**Quick commands:**
```bash
pylint src/orchestrator/
flake8 src/orchestrator/
bandit -r src/orchestrator/
```

---

## 9. Industry Professional Practices

**What you learn:**
- Professional Git workflow: branch naming, PR process, commit message conventions.
- How to present this project in a job interview or internship application.
- Turning academic deliverables into portfolio artifacts.
- Agile sprint ceremonies adapted for a student team.
- Documentation standards that matter in industry (README, architecture diagrams, API docs).

**Reference document:**
```
docs/Industry_Experience_Guide.md
```

---

## 10. Reference Code in the Template

These are working code examples (not to copy verbatim, but to learn from):

| File | What it demonstrates |
|------|----------------------|
| `src/core/llm_client.py` | Full US-001 LLM abstraction layer implementation |
| `src/core/config.yaml` | Multi-provider configuration structure |
| `src/agents/coder_agent.py` | Coder agent skeleton with prompt integration |
| `src/agents/tester_agent.py` | Tester agent skeleton |
| `prompt_templates.py` | Prompt template constants |
| `example_usage_multimodal.py` | Provider switching, rate limit handling, cost patterns |
| `examples/old/ollama_client.py` | Local Ollama client example |

---

## Quick Navigation Cheat Sheet

| I need to understand... | Go to |
|------------------------|-------|
| What the project is supposed to do | `docs/AI_CodeDevelopment_ProblemDefinition.md` |
| A specific user story's requirements | `docs/planning/User_Stories_Sprint_Plan.md` |
| How the state machine works | `docs/Technical_Implementation_Guide.md` §1 |
| How to call the LLM | `docs/guides/LLM_API_GUIDE.md` |
| How to get a free API key | `docs/guides/QUICKSTART_LLM.md` |
| Groq-specific setup | `docs/guides/GROQ_GUIDE.md` |
| Claude-specific setup | `docs/guides/CLAUDE_GUIDE.md` |
| How to write good prompts | `docs/AI_CodeDevelopment_ProblemDefinition.md` Appendix A |
| Evaluation/grading criteria | `docs/AI_CodeDevelopment_ProblemDefinition.md` §9 & §10 |
| Industry value / interviews | `docs/Industry_Experience_Guide.md` |

---

*Last updated: April 2026. Template base path is a local server path — contact the project supervisor if the template directory has moved.*
