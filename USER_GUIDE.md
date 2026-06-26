# AI Development Orchestrator — User Guide

A production-grade, Human-in-the-Loop (HITL) pipeline that uses AI agents to generate, test, review, and validate Python code — with **you** in control at every step.

---

## Table of Contents

1. [Installation & Setup](#installation--setup)
2. [CLI Commands](#cli-commands)
3. [Workflow Overview](#workflow-overview)
4. [Checkpoint 1 — Code Review](#checkpoint-1--code-review)
5. [Checkpoint 2 — Test Results](#checkpoint-2--test-results)
6. [Checkpoint 3 — Final Review](#checkpoint-3--final-review)
7. [How to Edit Code Directly](#how-to-edit-code-directly)
8. [Understanding the Feedback Table](#understanding-the-feedback-table)
9. [Guardrail Warnings](#guardrail-warnings)
10. [Tips & Best Practices](#tips--best-practices)

---

## Installation & Setup

### 1. Clone and install

```bash
cd ai-driven-development-automation
pip install -e .
```

### 2. Set your Gemini API key

```bash
# Windows PowerShell
$env:GEMINI_API_KEY = "your-api-key-here"

# Linux / macOS
export GEMINI_API_KEY="your-api-key-here"
```

### 3. Verify

```bash
ai-orchestrator --help
```

You should see three commands: `generate`, `validate`, `complete`.

---

## CLI Commands

### `generate` — Create code from scratch

```bash
ai-orchestrator generate "Create a Python function that calculates compound interest"
```

The AI Coder Agent writes the code from your natural-language description.

### `validate` — Improve existing code

```bash
ai-orchestrator validate path/to/your_file.py
```

Feeds your existing file into the pipeline for review, testing, and improvement.

### `complete` — Fill in a code skeleton

```bash
ai-orchestrator complete skeleton.py "Implement all TODO functions with proper error handling"
```

Reads your skeleton file and tells the AI to implement the missing parts.

---

## Workflow Overview

The pipeline runs in a loop with **3 human checkpoints** and up to **4 attempts** (1 initial + 3 retries):

```
┌─────────────┐
│ Coder Agent │  ← Generates or fixes code
└──────┬──────┘
       ▼
╔══════════════════╗
║ CHECKPOINT 1     ║  ← You review the code
║ Code Review      ║     [a]pprove / [r]eject / [e]dit
╚══════╤═══════════╝
       ▼
┌──────────────┐
│ Tester Agent │  ← Generates & runs pytest
└──────┬───────┘
       ▼
╔══════════════════╗
║ CHECKPOINT 2     ║  ← You review test results
║ Test Results     ║     [a]pprove / [r]eject / [e]dit / [s]kip
╚══════╤═══════════╝
       ▼
┌─────────────────┐
│ Reviewer Agent  │  ← Semantic review + pylint
└──────┬──────────┘
       ▼
┌──────────────────┐
│ Validator Agent  │  ← Aggregates all issues
└──────┬───────────┘
       ▼
╔══════════════════╗
║ CHECKPOINT 3     ║  ← Final quality gate
║ Final Review     ║     [a]pprove / [r]eject / [e]dit
╚══════╤═══════════╝
       ▼
   ✅ DONE  or  ♻️ Loop back to Coder Agent
```

If you **reject** at any checkpoint, the pipeline loops back to the Coder Agent with your feedback attached as structured items. If you **approve** at Checkpoint 3, outputs are saved in a run-specific workspace at `output/runs/<run_id>/workspace/` with metrics and artifacts alongside it.

---

## Checkpoint 1 — Code Review

**What you see:**

- The full generated/fixed code with syntax highlighting and line numbers
- A color-coded **diff** (on retry iterations) showing exactly what changed
- **Guardrail warnings** if the AI changed code outside the scope of feedback
- Count of resolved feedback items from the previous iteration

**Actions:**

| Key | Action      | When to use                                                           |
| --- | ----------- | --------------------------------------------------------------------- |
| `a` | **Approve** | Code looks correct — proceed to testing                               |
| `r` | **Reject**  | Something is wrong — type feedback describing the issue               |
| `e` | **Edit**    | You want to fix the code yourself (paste code or provide a file path) |

**On reject:** You'll be prompted to type feedback. Be specific — include function names and what's wrong:

```
"The calculate_interest function doesn't handle negative principal values — add a ValueError check"
```

---

## Checkpoint 2 — Test Results

**What you see:**

- Pass/fail status and line coverage percentage
- Full pytest output in a bordered panel

**Actions:**

| Key | Action      | When to use                                                                                           |
| --- | ----------- | ----------------------------------------------------------------------------------------------------- |
| `a` | **Approve** | Tests pass and look correct — proceed to review                                                       |
| `r` | **Reject**  | Tests are bad or code needs fixing — type feedback                                                    |
| `e` | **Edit**    | You want to paste your own test code (replaces AI-generated tests, then pytest re-runs automatically) |
| `s` | **Skip**    | You don't care about tests right now — proceed with a warning                                         |

**On edit:** You can paste your own pytest code (type `END` on its own line when done), or provide a file path to a test file you already wrote. Pytest will re-run automatically with your tests.

---

## Checkpoint 3 — Final Review

**What you see:**

- **Metrics table** — execution time, lines of code, line/branch coverage, pylint score, security issues
- **Test failure details** (if tests failed)
- **Code review report** from the Reviewer Agent
- **Feedback items table** — all unresolved issues with severity and source

**Actions:**

| Key | Action      | When to use                                                    |
| --- | ----------- | -------------------------------------------------------------- |
| `a` | **Approve** | Everything looks good — persist run artifacts and finish        |
| `r` | **Reject**  | Not ready — provide feedback and loop back for another attempt |
| `e` | **Edit**    | Make a final manual fix before saving                          |

---

## How to Edit Code Directly

When you choose `[e]dit` at any checkpoint, you have three ways to provide code:

### Option 1: Paste code inline

When prompted, paste your corrected code directly. Type `END` on its own line to finish:

```
def add(a, b):
    return a + b
END
```

### Option 2: Provide a file path

Type the full path to a file on disk:

```
C:\Users\you\fixed_code.py
```

### Option 3: Provide short inline code

If your input is longer than 20 characters, it's treated as inline code automatically.

> **Note:** If you have multiple source files, you'll be asked which file to edit.

---

## Understanding the Feedback Table

The feedback table appears at Checkpoint 3 (and sometimes Checkpoint 1) showing all unresolved issues:

```
┌───┬──────────┬────────────────┬────────────┬──────────────────────────┬────────┐
│ # │ Source   │ Severity       │ Location   │ What To Fix              │ Status │
├───┼──────────┼────────────────┼────────────┼──────────────────────────┼────────┤
│ 1 │ reviewer │ 🔴 CRITICAL    │ add() L5   │ Division by zero not...  │ ❌ Open │
│ 2 │ tester   │ 🔴 CRITICAL    │ —          │ Tests failed: FAILED...  │ ❌ Open │
│ 3 │ reviewer │ 🟡 MAJOR       │ L12-L15    │ No input validation...   │ ❌ Open │
│ 4 │ human    │ 🟡 MAJOR       │ —          │ Add docstrings to all... │ ❌ Open │
│ 5 │ reviewer │ 🔵 MINOR       │ L3         │ Unused import os         │ ❌ Open │
│ 6 │ reviewer │ 💡 SUGGESTION  │ —          │ Consider using typing...  │ ❌ Open │
└───┴──────────┴────────────────┴────────────┴──────────────────────────┴────────┘
```

### Severity levels

| Icon | Level          | Meaning                                                  |
| ---- | -------------- | -------------------------------------------------------- |
| 🔴   | **CRITICAL**   | Must fix — code is broken, tests fail, or security issue |
| 🟡   | **MAJOR**      | Should fix — significant quality or correctness issue    |
| 🔵   | **MINOR**      | Nice to fix — style, naming, or minor improvement        |
| 💡   | **SUGGESTION** | Optional — best-practice recommendation                  |

### Sources

| Source      | Meaning                                  |
| ----------- | ---------------------------------------- |
| `tester`    | Issue found by running pytest            |
| `reviewer`  | Issue found by the AI Reviewer or pylint |
| `validator` | Issue aggregated by the Validator Agent  |
| `human`     | Feedback you typed at a checkpoint       |

Long descriptions are truncated to 4 lines in the table to keep it readable.

---

## Guardrail Warnings

If the AI Coder modifies code **outside the scope of the feedback**, you'll see guardrail warnings like:

```
🛡️ Guardrail Warnings
⚠️  Lines 30-39 were changed but no feedback item references them
⚠️  Function 'helper()' was removed — was this intentional?
```

**What to do:**

- If the changes look intentional and correct → **Approve**
- If the AI changed things it shouldn't have → **Reject** with feedback like "Only fix the add() function, don't touch helper()"
- If you want to revert the unwanted changes → **Edit** and paste the correct version

---

## Tips & Best Practices

1. **Be specific in your feedback.** Instead of "code is wrong", say "the `calculate()` function returns float but should return Decimal for currency precision".

2. **Use function names and line numbers** in reject feedback — the Coder Agent uses them to scope its fix.

3. **Approve early, iterate later.** If the code is 90% correct, approve at Checkpoint 1, let it run through testing and review, then fix the remaining issues at Checkpoint 3.

4. **Edit when the AI keeps getting it wrong.** After 2 failed attempts at fixing something, paste the correct code yourself using `[e]dit` — it's faster than another round-trip.

5. **Skip tests if you're prototyping.** Use `[s]kip` at Checkpoint 2 when you just want to see the generated code quickly.

6. **Edit tests when AI-generated tests are wrong.** Use `[e]dit` at Checkpoint 2 to paste your own pytest code — pytest will re-run automatically.

7. **Watch guardrail warnings.** They catch the AI silently rewriting code it wasn't asked to change.

8. **Check the metrics table** at Checkpoint 3 — if pylint score is below 8 or coverage below 80%, consider rejecting.

9. **Output files** are run-scoped under `output/runs/<run_id>/workspace/`. Metrics are in `output/runs/<run_id>/metrics/metrics.json`, and review/feedback artifacts are in `output/runs/<run_id>/artifacts/`.

10. **Max retries is 3.** After 4 total attempts (1 initial + 3 retries) the pipeline stops. If you're stuck, try rephrasing your requirements or using `[e]dit` to provide a starting point.
