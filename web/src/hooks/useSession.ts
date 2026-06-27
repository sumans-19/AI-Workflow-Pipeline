/* ─── REST API hook for session management ─── */

import { useCallback } from "react";
import { useSessionStore } from "../store/sessionStore";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function useSession() {
  const setSessionId = useSessionStore((s) => s.setSessionId);
  const setStatus = useSessionStore((s) => s.setStatus);
  const addMessage = useSessionStore((s) => s.addMessage);
  const reset = useSessionStore((s) => s.reset);

  const createSession = useCallback(
    async (prompt: string) => {
      const store = useSessionStore.getState();
      reset();

      addMessage({
        id: crypto.randomUUID(),
        role: "user",
        content: prompt,
        timestamp: Date.now(),
      });

      try {
        const res = await fetch(`${API_BASE}/api/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            prompt, 
            mode: "GENERATE",
            test_execution_mode: store.testExecutionMode
          }),
        });
        const data = await res.json();
        setSessionId(data.session_id);
        setStatus("running");
      } catch (err) {
        addMessage({
          id: crypto.randomUUID(),
          role: "system",
          content: `❌ Failed to start session: ${err}`,
          timestamp: Date.now(),
        });
        setStatus("error");
      }
    },
    [setSessionId, setStatus, addMessage, reset]
  );

  const sendAction = useCallback(
    async (action: string, feedback: string = "") => {
      const store = useSessionStore.getState();
      const sessionId = store.sessionId;
      if (!sessionId) return;

      try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/action`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, feedback }),
        });
        
        if (!res.ok) {
          throw new Error(`Server returned ${res.status}`);
        }
        
        // Optimistically update the UI to show the pipeline is running again
        store.setCheckpoint(null);
        store.setStatus("running");
      } catch (err) {
        console.error("Failed to send action:", err);
      }
    },
    []
  );

  return { createSession, sendAction };
}
