export interface Directive {
  id: string;
  title: string;
  category: "mission" | "trait" | "prohibition";
  description: string;
}

export interface ConstitutionPayload {
  name: string;
  version: string;
  directives: Directive[];
}

export interface SafetyEvaluation {
  allowed: boolean;
  risk_level: "safe" | "review" | "blocked";
  matched_rules: string[];
  reason: string;
  note: string;
}

export interface HealthPayload {
  status: string;
  service: string;
  version: string;
  stats: {
    learnings: number;
    reports: number;
    adaptations: number;
  };
}

export interface LearningEntry {
  id: number;
  topic: string;
  content: string;
  source: string;
  tags: string[];
  created_at: string;
}

export interface ReportEntry {
  id: number;
  title: string;
  summary: string;
  category: string;
  confidence: number;
  honest_gaps: string;
  created_at: string;
}

export interface AdaptationEntry {
  id: number;
  trigger: string;
  change: string;
  rationale: string;
  created_at: string;
}

export const DEFAULT_API_BASE =
  (import.meta as { env?: Record<string, string | undefined> }).env?.VITE_LAZARUS_API_URL ??
  "http://127.0.0.1:8000";

export function formatConfidence(confidence: number): string {
  const clamped = Math.max(0, Math.min(1, confidence));
  return `${Math.round(clamped * 100)}%`;
}

export function riskBadgeLabel(riskLevel: SafetyEvaluation["risk_level"]): string {
  switch (riskLevel) {
    case "safe":
      return "SAFE";
    case "review":
      return "NEEDS CREATOR CONFIRMATION";
    case "blocked":
      return "BLOCKED — NON-HARM RULE";
  }
}

async function requestJson<T>(
  baseUrl: string,
  path: string,
  init?: RequestInit,
  fetchImpl: typeof fetch = fetch,
): Promise<T> {
  const response = await fetchImpl(`${baseUrl.replace(/\/$/, "")}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`Lazarus API error (${response.status}): ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function createLazarusClient(baseUrl = DEFAULT_API_BASE, fetchImpl: typeof fetch = fetch) {
  return {
    getHealth: () => requestJson<HealthPayload>(baseUrl, "/health", undefined, fetchImpl),
    getConstitution: () =>
      requestJson<ConstitutionPayload>(baseUrl, "/constitution", undefined, fetchImpl),
    evaluateAction: (action: string) =>
      requestJson<SafetyEvaluation>(
        baseUrl,
        "/constitution/evaluate",
        { method: "POST", body: JSON.stringify({ action }) },
        fetchImpl,
      ),
    listLearnings: (query = "") =>
      requestJson<{ query: string; count: number; items: LearningEntry[] }>(
        baseUrl,
        `/learn?q=${encodeURIComponent(query)}`,
        undefined,
        fetchImpl,
      ),
    addLearning: (payload: {
      topic: string;
      content: string;
      source?: string;
      tags?: string[];
    }) =>
      requestJson<LearningEntry>(
        baseUrl,
        "/learn",
        { method: "POST", body: JSON.stringify(payload) },
        fetchImpl,
      ),
    listReports: () =>
      requestJson<{ count: number; items: ReportEntry[] }>(
        baseUrl,
        "/reports",
        undefined,
        fetchImpl,
      ),
    addReport: (payload: {
      title: string;
      summary: string;
      category?: string;
      confidence?: number;
      honest_gaps?: string;
    }) =>
      requestJson<ReportEntry>(
        baseUrl,
        "/reports",
        { method: "POST", body: JSON.stringify(payload) },
        fetchImpl,
      ),
    listAdaptations: () =>
      requestJson<{ count: number; items: AdaptationEntry[] }>(
        baseUrl,
        "/adaptations",
        undefined,
        fetchImpl,
      ),
    addAdaptation: (payload: { trigger: string; change: string; rationale: string }) =>
      requestJson<AdaptationEntry>(
        baseUrl,
        "/adaptations",
        { method: "POST", body: JSON.stringify(payload) },
        fetchImpl,
      ),
  };
}
