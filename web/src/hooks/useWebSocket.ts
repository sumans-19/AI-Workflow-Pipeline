/* ─── WebSocket hook — connects to backend, dispatches events to store ─── */

import { useCallback, useEffect, useRef } from "react";
import { useSessionStore } from "../store/sessionStore";
import type {
  CheckpointData,
  FileCreatedData,
  LogData,
  MetricsData,
  PipelineCompleteData,
  ReviewReportData,
  StageUpdateData,
  TestResultsData,
  WSEvent,
} from "../types";

const WS_BASE = import.meta.env.VITE_WS_URL || "ws://localhost:8000";
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const sessionId = useSessionStore((s) => s.sessionId);

  // Use a ref-based handler so we always access the latest store state
  // without needing to recreate the WebSocket connection.
  const handleEventRef = useRef<(event: WSEvent) => void>(() => {});

  handleEventRef.current = (event: WSEvent) => {
    const { type, data } = event;
    const store = useSessionStore.getState();

    console.log("[WS] Event received:", type, data);

    switch (type) {
      case "pipeline_started":
        store.setStatus("running");
        store.addMessage({
          id: crypto.randomUUID(),
          role: "system",
          content: "🚀 Pipeline started…",
          timestamp: Date.now(),
        });
        break;

      case "stage_update": {
        const d = data as StageUpdateData;
        if (d.status === "in_progress") {
          store.addTimelineStep({
            stage: d.stage,
            status: "in_progress",
            message: d.message,
            timestamp: Date.now(),
          });
        } else {
          store.updateTimelineStep(d.stage, {
            status: d.status,
            message: d.message,
          });
        }
        store.addMessage({
          id: crypto.randomUUID(),
          role: "assistant",
          content: d.message,
          timestamp: Date.now(),
        });
        break;
      }

      case "agent_started": {
        const d = data as any;
        const stageName = d.agent === "tester" ? "TESTING" : d.agent.toUpperCase();
        store.addTimelineStep({
          stage: stageName,
          status: "in_progress",
          message: `${d.agent} started...`,
          timestamp: Date.now(),
        });
        break;
      }

      case "agent_progress": {
        const d = data as any;
        const stageName = d.agent === "tester" ? "TESTING" : d.agent.toUpperCase();
        store.updateTimelineStep(stageName, {
          status: "in_progress",
          message: d.message || `${d.progress}% complete`,
        });
        break;
      }

      case "agent_completed": {
        const d = data as any;
        const stageName = d.agent === "tester" ? "TESTING" : d.agent.toUpperCase();
        store.updateTimelineStep(stageName, {
          status: d.failed ? "error" : "complete",
          message: d.message || `${d.agent} completed`,
        });
        store.addMessage({
          id: crypto.randomUUID(),
          role: "assistant",
          content: `✅ ${d.agent} finished successfully.`,
          timestamp: Date.now(),
        });
        break;
      }

      case "agent_failed": {
        const d = data as any;
        const stageName = d.agent === "tester" ? "TESTING" : d.agent.toUpperCase();
        store.updateTimelineStep(stageName, {
          status: "error",
          message: d.reason || `${d.agent} failed`,
        });
        break;
      }

      case "file_created": {
        const d = data as FileCreatedData;
        store.addFile(d.path, d.content, d.language);
        // Auto-select the first file so Code tab is not empty
        const currentSelected = store.selectedFile;
        if (!currentSelected) {
          store.selectFile(d.path);
        }
        store.addMessage({
          id: crypto.randomUUID(),
          role: "assistant",
          content: `📄 Created \`${d.path}\``,
          timestamp: Date.now(),
        });
        break;
      }

      case "file_updated": {
        const d = data as FileCreatedData;
        store.updateFileContent(d.path, d.content);
        break;
      }

      case "test_results": {
        const d = data as TestResultsData;
        store.setTestResults(d);
        break;
      }

      case "review_report": {
        const d = data as ReviewReportData;
        store.setReviewIssues(d.issues);
        break;
      }

      case "checkpoint": {
        const d = data as CheckpointData;
        store.setCheckpoint(d);
        store.setStatus("checkpoint");
        break;
      }

      case "metrics": {
        const d = data as MetricsData;
        store.setMetrics(d);
        break;
      }

      case "log": {
        const d = data as LogData;
        store.addMessage({
          id: crypto.randomUUID(),
          role: "system",
          content: d.message,
          timestamp: Date.now(),
        });
        break;
      }

      case "pipeline_complete": {
        const d = data as PipelineCompleteData;
        store.setStatus(d.status === "success" ? "complete" : "error");
        store.setCheckpoint(null);
        store.addMessage({
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            d.status === "success"
              ? "✅ Pipeline complete! Code is ready."
              : `❌ Pipeline ended: ${d.message || d.status}`,
          timestamp: Date.now(),
        });
        break;
      }

      default:
        console.log("[WS] Unhandled event:", type, data);
    }
  };

  useEffect(() => {
    if (!sessionId) return;
    
    let reconnectTimeoutId: NodeJS.Timeout;
    let isMounted = true;

    const connect = () => {
      const ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`);
      wsRef.current = ws;

      ws.onopen = async () => {
        console.log("[WS] Connected to session:", sessionId);
        try {
          const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/status`);
          if (res.ok) {
            const data = await res.json();
            const store = useSessionStore.getState();
            if (data.status) {
              store.setStatus(data.status);
            }
          }
        } catch (e) {
          console.error("[WS] Failed to sync session status:", e);
        }
      };

      ws.onmessage = (event) => {
        try {
          const parsed: WSEvent = JSON.parse(event.data);
          handleEventRef.current(parsed);
        } catch {
          console.warn("[WS] Failed to parse message:", event.data);
        }
      };

      ws.onerror = (e) => console.error("[WS] Error:", e);
      
      ws.onclose = (e) => {
        console.log("[WS] Disconnected, code:", e.code, "reason:", e.reason);
        if (isMounted) {
          console.log("[WS] Attempting to reconnect in 2s...");
          reconnectTimeoutId = setTimeout(connect, 2000);
        }
      };
    };

    connect();

    return () => {
      isMounted = false;
      clearTimeout(reconnectTimeoutId);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [sessionId]);

  /** Send a checkpoint response through the WebSocket */
  const sendCheckpointResponse = useCallback(
    (action: string, feedback: string = "") => {
      const store = useSessionStore.getState();
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        console.log("[WS] Sending checkpoint response:", action, feedback);
        wsRef.current.send(
          JSON.stringify({ type: "checkpoint_response", action, feedback })
        );
        store.setCheckpoint(null);
        store.setStatus("running");
      } else {
        console.warn("[WS] Cannot send checkpoint response — WebSocket not open, readyState:", wsRef.current?.readyState);
      }
    },
    []
  );

  return { sendCheckpointResponse };
}
