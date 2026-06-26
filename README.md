# ai-driven-development-automation

An AI-powered, Human-in-the-Loop (HITL) pipeline that uses specialized agents to generate, test, review, and validate Python code — with you in control at every step.

---

## Architecture Diagram

```mermaid
graph TB
    subgraph CLI["🖥️ CLI Layer (main.py)"]
        GEN["generate<br/><i>Create code from prompt</i>"]
        VAL["validate<br/><i>Improve existing file</i>"]
        COMP["complete<br/><i>Fill in skeleton code</i>"]
    end

    subgraph CONFIG["⚙️ Configuration (config.py)"]
        SETTINGS["Settings<br/><i>GEMINI_API_KEY, MODEL,<br/>BASE_URL</i>"]
    end

    subgraph ORCHESTRATION["🔄 Orchestration Layer"]
        WF["WorkflowOrchestrator<br/>(workflow.py)<br/><i>Manages agent sequence,<br/>checkpoints &amp; retry loop<br/>(max 3 retries)</i>"]
        CTX["WorkflowContext<br/>(context.py)<br/><i>Pipeline state: source_code,<br/>test_results, feedback_items,<br/>metrics, code_history</i>"]
        GR["Guardrails<br/>(guardrails.py)<br/><i>validate_fix_scope: changes<br/>match feedback locations<br/>check_preservation: no<br/>accidental deletions (AST)</i>"]
    end

    subgraph AGENTS["🤖 Agent Layer"]
        direction LR
        CODER["Coder Agent<br/>(coder.py)<br/><i>generate / validate /<br/>complete / fix code</i>"]
        TESTER["Tester Agent<br/>(tester.py)<br/><i>Generate pytest suite<br/>&amp; run tests</i>"]
        REVIEWER["Reviewer Agent<br/>(reviewer.py)<br/><i>LLM semantic review<br/>+ pylint analysis</i>"]
        VALIDATOR["Validator Agent<br/>(validator.py)<br/><i>Aggregate issues,<br/>set pass/fail</i>"]
    end

    subgraph LLM["🧠 LLM Integration"]
        GEMINI["GeminiClient<br/>(gemini_client.py)<br/><i>Gemini 2.5 Flash via<br/>OpenAI-compatible API<br/>Rate limit handling &amp;<br/>retry logic</i>"]
    end

    subgraph TOOLS["🔧 Tools Layer"]
        FM["FileManager<br/>(file_manager.py)<br/><i>Read/write source &amp;<br/>test files to output/</i>"]
        PR["PythonRunner<br/>(python_runner.py)<br/><i>Run pytest with<br/>coverage reporting</i>"]
    end

    subgraph HUMAN["👤 Human-in-the-Loop (console.py)"]
        CP1["Checkpoint 1<br/>Code Review<br/><i>approve / reject / edit</i>"]
        CP2["Checkpoint 2<br/>Test Results<br/><i>approve / reject / edit / skip</i>"]
        CP3["Checkpoint 3<br/>Final Review<br/><i>approve / reject / edit</i>"]
    end

    subgraph FEEDBACK["📋 Feedback System (context.py)"]
        FBI["FeedbackItem<br/><i>source: human | reviewer |<br/>tester | validator<br/>severity: critical | major |<br/>minor | suggestion<br/>location, description,<br/>resolved flag</i>"]
    end

    OUTPUT[("📁 output/<br/><i>Final approved code<br/>&amp; test files</i>")]

    %% CLI to Orchestrator
    GEN --> WF
    VAL --> WF
    COMP --> WF
    SETTINGS -.->|API key &amp; model config| GEMINI

    %% Orchestrator manages everything
    WF -->|"1. Invoke"| CODER
    WF -->|"2. Checkpoint"| CP1
    WF -->|"3. Invoke"| TESTER
    WF -->|"4. Checkpoint"| CP2
    WF -->|"5. Invoke"| REVIEWER
    WF -->|"6. Invoke"| VALIDATOR
    WF -->|"7. Checkpoint"| CP3
    WF <-->|read/update state| CTX

    %% Agent interactions
    CODER <-->|prompts &amp; responses| GEMINI
    TESTER <-->|generate tests| GEMINI
    REVIEWER <-->|semantic review| GEMINI
    CODER -->|writes code| FM
    TESTER -->|writes tests &amp; runs| PR
    TESTER -->|writes test files| FM
    REVIEWER -->|runs pylint| PR

    %% Guardrails
    GR -.->|scope &amp; preservation checks| CODER

    %% Human checkpoint flows
    CP1 -->|approve| TESTER
    CP1 -->|"reject + feedback"| FBI
    CP2 -->|approve| REVIEWER
    CP2 -->|"reject + feedback"| FBI
    CP3 -->|approve| OUTPUT
    CP3 -->|"reject + feedback"| FBI

    %% Feedback loop
    FBI -->|"unresolved items<br/>fed back to"| CODER

    %% Styling
    classDef cliStyle fill:#4A90D9,stroke:#2C5F8A,color:#fff
    classDef agentStyle fill:#F5A623,stroke:#C07D12,color:#fff
    classDef llmStyle fill:#7B68EE,stroke:#5A4DB0,color:#fff
    classDef toolStyle fill:#50C878,stroke:#3A9A5C,color:#fff
    classDef humanStyle fill:#FF6B6B,stroke:#CC4444,color:#fff
    classDef stateStyle fill:#FFD700,stroke:#B8A000,color:#333
    classDef outputStyle fill:#2ECC71,stroke:#1A9B50,color:#fff

    class GEN,VAL,COMP cliStyle
    class CODER,TESTER,REVIEWER,VALIDATOR agentStyle
    class GEMINI llmStyle
    class FM,PR toolStyle
    class CP1,CP2,CP3 humanStyle
    class CTX,FBI,GR stateStyle
    class OUTPUT outputStyle
```

---

## Pipeline Flow

```mermaid
flowchart TD
    START([🚀 User runs CLI command]) --> INIT["Initialize WorkflowContext<br/><i>mode: GENERATE | VALIDATE | HYBRID</i>"]
    INIT --> LOOP{"Retry ≤ 3?"}

    LOOP -->|Yes| CODER["🤖 Coder Agent<br/><i>Generate, fix, validate,<br/>or complete code via LLM</i>"]
    LOOP -->|"No (max retries)"| REJECTED([❌ Pipeline Rejected])

    CODER --> GUARD{"🛡️ Guardrails<br/><i>Scope &amp; preservation<br/>checks pass?</i>"}
    GUARD -->|warnings| CP1
    GUARD -->|clean| CP1

    CP1{"👤 Checkpoint 1<br/>Code Review"}
    CP1 -->|"✅ Approve"| SAVE1["Save code to output/"]
    CP1 -->|"✏️ Edit"| APPLY["Apply human edit"] --> SAVE1
    CP1 -->|"❌ Reject + feedback"| BUMP1["retry_count++"] --> LOOP

    SAVE1 --> TESTER["🧪 Tester Agent<br/><i>Generate pytest suite,<br/>run tests, collect coverage</i>"]

    TESTER --> CP2{"👤 Checkpoint 2<br/>Test Results"}
    CP2 -->|"✅ Approve"| REVIEW
    CP2 -->|"⏭️ Skip"| REVIEW
    CP2 -->|"✏️ Edit tests"| RERUN["Re-run pytest<br/>with human tests"] --> REVIEW
    CP2 -->|"❌ Reject + feedback"| BUMP2["retry_count++"] --> LOOP

    REVIEW["🔍 Reviewer Agent<br/><i>LLM semantic review<br/>+ pylint static analysis</i>"]
    REVIEW --> VALIDATE["✔️ Validator Agent<br/><i>Aggregate issues, check<br/>test pass &amp; severity</i>"]

    VALIDATE --> CP3{"👤 Checkpoint 3<br/>Final Review"}
    CP3 -->|"✅ Approve"| DONE([✅ Pipeline Complete<br/><i>Files saved to output/</i>])
    CP3 -->|"✏️ Edit"| SAVEFINAL["Save edited code"] --> DONE
    CP3 -->|"❌ Reject + feedback"| BUMP3["retry_count++"] --> LOOP

    %% Styling
    classDef checkpoint fill:#FF6B6B,stroke:#CC4444,color:#fff
    classDef agent fill:#F5A623,stroke:#C07D12,color:#fff
    classDef success fill:#2ECC71,stroke:#1A9B50,color:#fff
    classDef fail fill:#E74C3C,stroke:#C0392B,color:#fff

    class CP1,CP2,CP3 checkpoint
    class CODER,TESTER,REVIEW,VALIDATE agent
    class DONE,SAVE1,SAVEFINAL success
    class REJECTED fail
```

---

## Component Details

| Layer             | Component            | File               | Responsibility                                                                                  |
| ----------------- | -------------------- | ------------------ | ----------------------------------------------------------------------------------------------- |
| **CLI**           | Typer Commands       | `main.py`          | Entry point — `generate`, `validate`, `complete` commands                                       |
| **Config**        | Settings             | `config.py`        | Manages `GEMINI_API_KEY`, model name, and base URL                                              |
| **Orchestration** | WorkflowOrchestrator | `workflow.py`      | Runs the agent sequence, manages checkpoints and retry loop                                     |
| **Orchestration** | WorkflowContext      | `context.py`       | Carries pipeline state: source code, test results, metrics, feedback, code history              |
| **Orchestration** | Guardrails           | `guardrails.py`    | Validates fix scope (changes match feedback) and preservation (no accidental deletions via AST) |
| **Agents**        | CoderAgent           | `coder.py`         | Generates, fixes, validates, or completes code via LLM prompts                                  |
| **Agents**        | TesterAgent          | `tester.py`        | Generates pytest test suites via LLM, runs them, collects coverage                              |
| **Agents**        | ReviewerAgent        | `reviewer.py`      | Performs LLM semantic review + pylint static analysis, emits FeedbackItems                      |
| **Agents**        | ValidatorAgent       | `validator.py`     | Aggregates issues from all sources, sets pipeline pass/fail                                     |
| **LLM**           | GeminiClient         | `gemini_client.py` | Gemini 2.5 Flash via OpenAI-compatible API with rate-limit handling and retries                 |
| **Tools**         | FileManager          | `file_manager.py`  | Reads and writes source/test files to the `output/` directory                                   |
| **Tools**         | PythonRunner         | `python_runner.py` | Runs `pytest --cov` and parses coverage percentage                                              |
| **UI**            | Console              | `console.py`       | Rich-based TUI: syntax highlighting, diffs, feedback tables, metrics, human prompts             |
| **Data**          | FeedbackItem         | `context.py`       | Structured issue record: source, severity, location, description, resolved flag                 |
