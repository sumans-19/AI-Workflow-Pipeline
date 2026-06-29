/* ─── Zustand store — single source of truth for the entire UI ─── */

import { create } from "zustand";
import type {
  ChatMessage,
  CheckpointData,
  FileNode,
  MetricsData,
  PlanningConfig,
  PlanningDocument,
  PlanningModuleId,
  SessionStatus,
  TestResultsData,
  TimelineStep,
} from "../types";

// All 15 planning module ids in canonical order.
const ALL_MODULE_IDS: PlanningModuleId[] = [
  "project_understanding",
  "functional_requirements",
  "folder_structure",
  "architecture_design",
  "component_breakdown",
  "dependency_planning",
  "data_flow",
  "file_responsibilities",
  "api_planning",
  "database_planning",
  "security_considerations",
  "testing_strategy",
  "code_standards",
  "risks_challenges",
  "execution_roadmap",
];

interface SessionState {
  /* Session */
  sessionId: string | null;
  status: SessionStatus;
  testExecutionMode: 'docker' | 'local';

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

  /* UI panel state */
  reviewOpen: boolean;
  explorerOpen: boolean;

  /* ── Planning ── */
  planningConfig: PlanningConfig;
  planningDocument: PlanningDocument | null;
  planningMode: 'config' | 'review' | 'idle';
  planningModulesGenerated: string[];

  /* Actions */
  setSessionId: (id: string) => void;
  setStatus: (s: SessionStatus) => void;
  setTestExecutionMode: (mode: 'docker' | 'local') => void;
  toggleReview: () => void;
  toggleExplorer: () => void;

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

  setPlanningConfig: (cfg: PlanningConfig) => void;
  togglePlanningModule: (moduleId: string, enabled: boolean) => void;
  selectAllPlanningModules: (enabled: boolean) => void;
  setPlanningDocument: (doc: PlanningDocument | null, generated?: string[]) => void;
  setPlanningMode: (mode: 'config' | 'review' | 'idle') => void;

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
  testExecutionMode: "docker" as "docker" | "local",
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
  reviewOpen: true as boolean,
  explorerOpen: true as boolean,
  // ── Planning defaults: NONE selected — user picks modules explicitly ──
  planningConfig: { modules: ALL_MODULE_IDS.reduce((acc, id) => ({ ...acc, [id]: false }), {}) } as PlanningConfig,
  planningDocument: null as PlanningDocument | null,
  planningMode: "config" as "config" | "review" | "idle",
  planningModulesGenerated: [] as string[],
};

// Separate record to track languages (not persisted in state directly)
const _fileLangs: Record<string, string> = {};

export const useSessionStore = create<SessionState>((set, _get) => ({
  ...initialState,

  setSessionId: (id) => set({ sessionId: id }),
  setStatus: (s) => set({ status: s }),
  setTestExecutionMode: (mode) => set({ testExecutionMode: mode }),
  toggleReview: () => set((st) => ({ reviewOpen: !st.reviewOpen })),
  toggleExplorer: () => set((st) => ({ explorerOpen: !st.explorerOpen })),

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

  setPlanningConfig: (cfg) => set({ planningConfig: cfg }),
  togglePlanningModule: (moduleId, enabled) =>
    set((st) => ({
      planningConfig: {
        ...st.planningConfig,
        modules: {
          ...st.planningConfig.modules,
          [moduleId]: enabled,
        },
      },
    })),
  selectAllPlanningModules: (enabled) =>
    set((st) => {
      const updatedModules = { ...st.planningConfig.modules };
      for (const id of ALL_MODULE_IDS) {
        updatedModules[id] = enabled;
      }
      return {
        planningConfig: {
          ...st.planningConfig,
          modules: updatedModules,
        },
      };
    }),
  setPlanningDocument: (doc, generated) =>
    set({
      planningDocument: doc,
      planningModulesGenerated: generated || [],
    }),
  setPlanningMode: (mode) => set({ planningMode: mode }),

  reset: () => {
    Object.keys(_fileLangs).forEach((k) => delete _fileLangs[k]);
    set({ ...initialState, recentlyAdded: new Set<string>() });
  },
}));
