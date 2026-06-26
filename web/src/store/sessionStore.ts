/* ─── Zustand store — single source of truth for the entire UI ─── */

import { create } from "zustand";
import type {
  ChatMessage,
  CheckpointData,
  FileNode,
  MetricsData,
  SessionStatus,
  TestResultsData,
  TimelineStep,
} from "../types";

interface SessionState {
  /* Session */
  sessionId: string | null;
  status: SessionStatus;

  /* Chat */
  messages: ChatMessage[];

  /* File explorer */
  files: FileNode[];
  selectedFile: string | null;
  fileContents: Record<string, string>;

  /* Timeline */
  timeline: TimelineStep[];

  /* Checkpoint */
  activeCheckpoint: CheckpointData | null;

  /* Results */
  testResults: TestResultsData | null;
  metrics: MetricsData | null;
  reviewIssues: string[];

  /* Recently added files (for highlight animation) */
  recentlyAdded: Set<string>;

  /* Actions */
  setSessionId: (id: string) => void;
  setStatus: (s: SessionStatus) => void;

  addMessage: (msg: ChatMessage) => void;

  addFile: (path: string, content: string, language: string) => void;
  updateFileContent: (path: string, content: string) => void;
  selectFile: (path: string | null) => void;

  addTimelineStep: (step: TimelineStep) => void;
  updateTimelineStep: (stage: string, update: Partial<TimelineStep>) => void;

  setCheckpoint: (cp: CheckpointData | null) => void;
  setTestResults: (r: TestResultsData) => void;
  setMetrics: (m: MetricsData) => void;
  setReviewIssues: (issues: string[]) => void;

  reset: () => void;
}

/* ── Build a tree from flat file paths ── */
function buildTree(files: Record<string, string>, languages: Record<string, string>): FileNode[] {
  const root: FileNode[] = [];

  for (const filePath of Object.keys(files)) {
    const parts = filePath.split("/");
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const name = parts[i];
      const isLast = i === parts.length - 1;
      const pathSoFar = parts.slice(0, i + 1).join("/");

      let node = current.find((n) => n.name === name);
      if (!node) {
        node = {
          name,
          path: pathSoFar,
          isDirectory: !isLast,
          children: [],
          content: isLast ? files[filePath] : undefined,
          language: isLast ? languages[filePath] : undefined,
        };
        current.push(node);
      }
      current = node.children;
    }
  }

  // Sort: directories first, then alphabetical
  const sortNodes = (nodes: FileNode[]) => {
    nodes.sort((a, b) => {
      if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((n) => sortNodes(n.children));
  };
  sortNodes(root);
  return root;
}

const initialState = {
  sessionId: null as string | null,
  status: "pending" as SessionStatus,
  messages: [] as ChatMessage[],
  files: [] as FileNode[],
  selectedFile: null as string | null,
  fileContents: {} as Record<string, string>,
  timeline: [] as TimelineStep[],
  activeCheckpoint: null as CheckpointData | null,
  testResults: null as TestResultsData | null,
  metrics: null as MetricsData | null,
  reviewIssues: [] as string[],
  recentlyAdded: new Set<string>() as Set<string>,
};

// Separate record to track languages (not persisted in state directly)
const _fileLangs: Record<string, string> = {};

export const useSessionStore = create<SessionState>((set, _get) => ({
  ...initialState,

  setSessionId: (id) => set({ sessionId: id }),
  setStatus: (s) => set({ status: s }),

  addMessage: (msg) => set((st) => ({ messages: [...st.messages, msg] })),

  addFile: (path, content, language) => {
    _fileLangs[path] = language;
    set((st) => {
      const newContents = { ...st.fileContents, [path]: content };
      const newRecent = new Set(st.recentlyAdded);
      newRecent.add(path);
      // Remove from recentlyAdded after 3 seconds
      setTimeout(() => {
        set((s) => {
          const updated = new Set(s.recentlyAdded);
          updated.delete(path);
          return { recentlyAdded: updated };
        });
      }, 3000);
      return {
        fileContents: newContents,
        files: buildTree(newContents, _fileLangs),
        recentlyAdded: newRecent,
      };
    });
  },

  updateFileContent: (path, content) => {
    set((st) => {
      const newContents = { ...st.fileContents, [path]: content };
      return {
        fileContents: newContents,
        files: buildTree(newContents, _fileLangs),
      };
    });
  },

  selectFile: (path) => set({ selectedFile: path }),

  addTimelineStep: (step) =>
    set((st) => ({ timeline: [...st.timeline, step] })),

  updateTimelineStep: (stage, update) =>
    set((st) => ({
      timeline: st.timeline.map((s) =>
        s.stage === stage ? { ...s, ...update } : s
      ),
    })),

  setCheckpoint: (cp) => set({ activeCheckpoint: cp }),
  setTestResults: (r) => set({ testResults: r }),
  setMetrics: (m) => set({ metrics: m }),
  setReviewIssues: (issues) => set({ reviewIssues: issues }),

  reset: () => {
    Object.keys(_fileLangs).forEach((k) => delete _fileLangs[k]);
    set({ ...initialState, recentlyAdded: new Set<string>() });
  },
}));
