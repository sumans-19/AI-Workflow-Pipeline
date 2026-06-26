# Advanced SDLC Automation Pipeline Plan

## 1. Architectural Improvements: Parent & Sub-Agent Architecture
**Current State**: The pipeline operates sequentially, which is basic and slow.
**Target State**: A hierarchical, parallel execution model similar to advanced agentic frameworks (like Claude Code or OpenCode).

### Agent Hierarchy
- **Parent Agent (Orchestrator)**: 
  - Acts as the project manager.
  - Analyzes the user request and breaks it down into discrete sub-tasks.
  - Delegates tasks to specialized Sub-Agents.
  - Merges outputs and resolves conflicts.
- **Specialized Sub-Agents**:
  - *Architect Agent*: Designs the folder structure and tech stack.
  - *Frontend Coder Agent*: Handles UI/UX generation.
  - *Backend Coder Agent*: Handles API, models, and business logic.
  - *Tester Agent*: Writes and runs tests.
  - *Reviewer Agent*: Reviews the generated code for security, best practices, and code quality (acts as an automated code reviewer).
  - *Validator Agent*: Validates the entire output against the original user prompt to ensure requirements are met before finalizing.
  - *DevOps Agent*: Handles Docker, CI/CD, and configurations.

### Parallel Execution
- Utilize Python's `asyncio` or `concurrent.futures` to execute Sub-Agents concurrently. 
- Example: While the *Backend Agent* generates APIs, the *Frontend Agent* can generate the React/HTML interface simultaneously.

---

## 2. Long-term Memory Implementation (SQLite)
**Objective**: Give the orchestrator context awareness across sessions and runs to prevent repetitive mistakes and allow iterative development.

### Implementation Strategy
- **Database Engine**: SQLite (via Python's built-in `sqlite3` or an ORM like `SQLAlchemy`).
- **Schema Design**:
  - `Sessions`: Track high-level user requests and project metadata.
  - `AgentLogs`: Store inputs, outputs, and reasoning of every agent execution.
  - `ContextState`: Store structural knowledge (e.g., chosen tech stack, file trees, API contracts) to be quickly queried by the Parent Agent.
- **Workflow**:
  - Upon starting, the Parent Agent loads previous context from SQLite.
  - Sub-agents save their progress to SQLite so the Tester or Reviewer agents can access the exact state without passing massive contexts in memory.

---

## 3. Resolving Current `TesterAgent` Issues
**Symptom**: The Tester agent is running pytest against non-Python configuration files (`test_pyproject.toml`, `test_README.md`, etc.), and throwing syntax errors related to unterminated strings in generated code.

### Root Cause
1. `TesterAgent.execute()` iterates over `context.source_code.items()` but fails to filter out non-code files like `.md`, `.txt`, `.env`, and `.toml`.
2. The `CoderAgent` occasionally truncates code (like in `config.py`), leading to invalid syntax (e.g., `SyntaxError: unterminated triple-quoted string literal`).

### Fix Strategy
- **Filter Files in Tester**: Modify `src/orchestrator/agents/tester.py` to only generate test files for `.py` files.
- **Syntax Validation in Coder**: Introduce an `ast.parse` check in the `CoderAgent` to ensure the generated Python code is syntactically complete before passing it down the pipeline.

---

## 4. Step-by-Step Task Breakdown

### Phase 1: Database & Memory Foundation
- [ ] **Task 1.1**: Set up SQLite connection utility and define the database schema (Tables: `Projects`, `Sessions`, `Memory_Nodes`).
- [ ] **Task 1.2**: Implement a `MemoryManager` class to handle CRUD operations for context storage.
- [ ] **Task 1.3**: Integrate `MemoryManager` into `WorkflowContext` so state is persisted across different CLI runs.

### Phase 2: Immediate Bug Fixes (Tester & Coder)
- [ ] **Task 2.1**: Update `src/orchestrator/agents/tester.py` to add a `if not filename.endswith('.py'): continue` guard.
- [ ] **Task 2.2**: Update `TesterAgent` to avoid generating tests for `__init__.py` or pure config files.
- [ ] **Task 2.3**: Implement a quick syntax validator in the `CoderAgent` to catch truncated JSON or unclosed strings before the file is finalized.

### Phase 3: Implementing the Parent Agent
- [ ] **Task 3.1**: Create `ParentAgent` class inheriting from `BaseAgent`.
- [ ] **Task 3.2**: Implement task breakdown logic using the LLM to yield JSON structures of sub-tasks.
- [ ] **Task 3.3**: Refactor existing `CoderAgent` and `TesterAgent` to accept specific, isolated sub-tasks rather than the entire global context.
- [ ] **Task 3.4**: Integrate `ReviewerAgent` and `ValidatorAgent` into the workflow as quality gates to approve code before the Parent Agent marks the sub-task complete.

### Phase 4: Parallel Execution Engine
- [ ] **Task 4.1**: Refactor the main orchestrator loop to use `asyncio.gather()` for independent agent tasks.
- [ ] **Task 4.2**: Implement a synchronization step in the `ParentAgent` to combine parallel code generation results (e.g., merging backend and frontend into the final workspace).
- [ ] **Task 4.3**: Update the `TesterAgent` to run asynchronously as soon as a single module is generated, rather than waiting for the entire project to finish.

### Phase 5: UI/UX and Interactive CLI Improvements (Inspired by `ai-coding-agent`)
- [ ] **Task 5.1**: Build a comprehensive `TUI` (Terminal User Interface) class in `src/orchestrator/cli/tui.py` leveraging `rich` layouts, syntax highlighters, and live updating groups to stream agent text and format tool execution beautifully.
- [ ] **Task 5.2**: Implement an Interactive Shell Loop (REPL) in the CLI entry point allowing users to converse continuously with the agents.
- [ ] **Task 5.3**: Introduce slash commands (`/config`, `/model`, `/clear`, `/sessions`, `/checkpoint`) to allow real-time control over the session without restarting the script.
- [ ] **Task 5.4**: Introduce a `ToolConfirmation` / Approval Policy system, asking the user via `Prompt.ask` before executing sensitive commands (like shell scripts or file overwrites) in the workspace.
