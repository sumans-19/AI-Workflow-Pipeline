import asyncio
from typing import Optional, Any
from .planning_state import PlanningState
from .planning_service import PlanningService
from .planning_events import (
    create_planning_started_event,
    create_planning_progress_event,
    create_planning_checkpoint_event,
    create_planning_failed_event,
    create_planning_completed_event
)
from ..core.context import WorkflowContext
from ..logging_config import logger

async def run_planning_stage(
    context: WorkflowContext,
    ws_manager: Any,
    session_id: str,
    planning_service: Optional[PlanningService] = None
) -> None:
    """
    Executes the planning stage asynchronously, handling WebSocket events
    and waiting for user approval.
    """
    if context.plan_approved:
        logger.info("Plan already approved, skipping planning stage.")
        return

    service = planning_service or PlanningService()

    # Initialize state
    state = PlanningState(
        requirements=context.requirements,
        project_name=context.project_name,
        project_type=context.project_type,
        selected_modules=context.planning_modules,
        status="in_progress"
    )

    logger.info("Starting planning stage for session %s", session_id)

    # Count how many modules were selected by the user.
    sel_modules = sorted([m for m, on in context.planning_modules.items() if on])
    sel_count = len(sel_modules)
    project_name = context.project_name or "your project"

    # ── 1. Visible chat messages ─────────────────────────────────────
    # Log events are routed to the chat window by useWebSocket. Emit a
    # sequence that walks the user through what the planner is doing.
    async def _chat(msg: str) -> None:
        await ws_manager.broadcast_to_session(session_id, {
            "type": "log",
            "data": {"message": msg},
        })

    await _chat(f"Planning Agent started — analyzing the request for **{project_name}**…")
    if sel_modules:
        await _chat(
            f" Selected planning modules ({sel_count}): "
            + ", ".join(f"`{m}`" for m in sel_modules)
        )
        await _chat(" Probing requirements & designing folder structure…")
    else:
        await _chat("⚠ No planning modules were selected — the planner will skip ahead.")

    # Emit stage_update so the sidebar pipeline UI shows PLANNING as running.
    await ws_manager.broadcast_to_session(session_id, {
        "type": "stage_update",
        "data": {
            "stage": "PLANNING",
            "status": "in_progress",
            "message": f"Planning Agent is analyzing your requirements ({sel_count} module(s))…",
        },
    })
    await ws_manager.broadcast_to_session(session_id, create_planning_started_event())
    await ws_manager.broadcast_to_session(session_id, create_planning_progress_event("Analyzing requirements and generating plan..."))

    # Run the agent in a thread so we don't block the event loop
    await _chat(" Calling the LLM to design the minimal Python file structure…")

    # ── Live progress ticker ─────────────────────────────────────────
    # The LLM call can take 10-30 seconds for big plans. Without a
    # ticker the middle chat section sits empty until the LLM responds.
    # We fire a "thinking…" message into the chat every ~5 seconds so the
    # user always sees that something is happening.
    import asyncio as _aio
    stop_tick = _aio.Event()

    async def _tick():
        phases = [
            "still thinking about project type & complexity…",
            "drafting folder structure…",
            "mapping components to modules…",
            "writing component breakdown…",
            "defining API surface & dependencies…",
            "reviewing the plan for consistency…",
        ]
        idx = 0
        while not stop_tick.is_set():
            try:
                await _aio.wait_for(stop_tick.wait(), timeout=5)
                return  # cancelled
            except _aio.TimeoutError:
                pass
            try:
                msg = phases[idx % len(phases)].rstrip("…")
                await _chat(f" {msg}…")
                await ws_manager.broadcast_to_session(session_id, {
                    "type": "agent_progress",
                    "data": {
                        "agent": "planner",
                        "message": msg,
                        "progress": min(95, 25 + idx * 12),
                    },
                })
            except Exception:
                pass
            idx += 1

    ticker_task = _aio.create_task(_tick())
    try:
        state = await _aio.to_thread(service.generate_plan, state, context)
    finally:
        stop_tick.set()
        try:
            await _aio.wait_for(ticker_task, timeout=1.0)
        except Exception:
            pass

    if state.status == "error":
        logger.error("Planning failed: %s", state.error_message)
        await ws_manager.broadcast_to_session(session_id, create_planning_failed_event(state.error_message))
        await _chat(f" Planning failed: {state.error_message}")
        # Mark the PLANNING stage as failed so the UI reflects it.
        await ws_manager.broadcast_to_session(session_id, {
            "type": "stage_update",
            "data": {
                "stage": "PLANNING",
                "status": "error",
                "message": state.error_message or "Planning Agent failed",
            },
        })
        context.success = False
        context.error_message = state.error_message
        return

    # Success -> Checkpoint
    logger.info("Planning generated successfully, waiting for approval...")

    plan_dict = {}
    if state.plan:
        # Convert the dataclass back to a dict for the frontend
        import dataclasses
        for field in dataclasses.fields(state.plan):
            val = getattr(state.plan, field.name)
            if val is not None:
                if dataclasses.is_dataclass(val):
                    plan_dict[field.name] = dataclasses.asdict(val)
                else:
                    plan_dict[field.name] = val

    modules_generated = state.plan.selected_module_ids() if state.plan else []

    # ── 2. Post-planning summary in the chat window ────────────────
    source_count = len([
        p for p in (getattr(getattr(state.plan, "folder_structure", None), "tree", "") or "").splitlines()
        if p.strip().endswith(".py")
    ])
    await _chat(
        f"Plan ready — {len(modules_generated)} module(s) generated; "
        f"~{source_count} Python source file(s) planned."
    )
    await _chat(" Plan written to the **Planning/** folder in the explorer.")
    await _chat(" Review the plan in the review panel and **Approve** to continue, or **Edit / Regenerate** to refine.")

    await ws_manager.broadcast_to_session(
        session_id,
        create_planning_checkpoint_event(
            plan=plan_dict,
            modules_selected=state.selected_modules,
            modules_generated=modules_generated,
            plan_markdown=state.plan_markdown
        )
    )

    # Wait for the user to approve the plan via the checkpoint mechanism
    # The WebWorkflowOrchestrator handles the actual pause/resume logic,
    # so we just mark the context as needing approval and return.
    context.current_step = "PLANNING_REVIEW"

    # Note: the actual waiting and parsing of the user's action (approve/edit/regenerate)
    # is handled in the orchestrator's run() loop, just like code review.
