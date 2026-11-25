import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AdaptationEntry,
  ConstitutionPayload,
  createLazarusClient,
  DEFAULT_API_BASE,
  formatConfidence,
  HealthPayload,
  LearningEntry,
  ReportEntry,
  riskBadgeLabel,
  SafetyEvaluation,
} from "./lib/api";

type TabKey = "learn" | "reports" | "adaptations" | "safety";

export function App() {
  const client = useMemo(() => createLazarusClient(DEFAULT_API_BASE), []);

  const [tab, setTab] = useState<TabKey>("learn");
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [constitution, setConstitution] = useState<ConstitutionPayload | null>(null);
  const [learnings, setLearnings] = useState<LearningEntry[]>([]);
  const [reports, setReports] = useState<ReportEntry[]>([]);
  const [adaptations, setAdaptations] = useState<AdaptationEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [learnTopic, setLearnTopic] = useState("");
  const [learnContent, setLearnContent] = useState("");
  const [learnTags, setLearnTags] = useState("");

  const [reportTitle, setReportTitle] = useState("");
  const [reportSummary, setReportSummary] = useState("");
  const [reportGaps, setReportGaps] = useState("");
  const [reportConfidence, setReportConfidence] = useState(0.9);

  const [adaptTrigger, setAdaptTrigger] = useState("");
  const [adaptChange, setAdaptChange] = useState("");
  const [adaptRationale, setAdaptRationale] = useState("");

  const [actionToCheck, setActionToCheck] = useState("");
  const [evaluation, setEvaluation] = useState<SafetyEvaluation | null>(null);

  const refreshAll = useCallback(async () => {
    try {
      const [h, c, l, r, a] = await Promise.all([
        client.getHealth(),
        client.getConstitution(),
        client.listLearnings(searchQuery),
        client.listReports(),
        client.listAdaptations(),
      ]);
      setHealth(h);
      setConstitution(c);
      setLearnings(l.items);
      setReports(r.items);
      setAdaptations(a.items);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? `${err.message}. Start the backend with: make dev-backend`
          : "Unable to reach Lazarus backend API.",
      );
    }
  }, [client, searchQuery]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  async function handleLearnSubmit(e: FormEvent) {
    e.preventDefault();
    if (!learnTopic.trim() || !learnContent.trim()) return;
    await client.addLearning({
      topic: learnTopic,
      content: learnContent,
      tags: learnTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    });
    setLearnTopic("");
    setLearnContent("");
    setLearnTags("");
    await refreshAll();
  }

  async function handleReportSubmit(e: FormEvent) {
    e.preventDefault();
    if (!reportTitle.trim() || !reportSummary.trim()) return;
    await client.addReport({
      title: reportTitle,
      summary: reportSummary,
      confidence: reportConfidence,
      honest_gaps: reportGaps,
    });
    setReportTitle("");
    setReportSummary("");
    setReportGaps("");
    await refreshAll();
  }

  async function handleAdaptSubmit(e: FormEvent) {
    e.preventDefault();
    if (!adaptTrigger.trim() || !adaptChange.trim() || !adaptRationale.trim()) return;
    await client.addAdaptation({
      trigger: adaptTrigger,
      change: adaptChange,
      rationale: adaptRationale,
    });
    setAdaptTrigger("");
    setAdaptChange("");
    setAdaptRationale("");
    await refreshAll();
  }

  async function handleSafetyCheck(e: FormEvent) {
    e.preventDefault();
    if (!actionToCheck.trim()) return;
    const res = await client.evaluateAction(actionToCheck);
    setEvaluation(res);
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">THE UNDERGROUND OFFICE</p>
          <h1>Lazarus Command Center</h1>
        </div>
        <div className="status-group">
          <span className={`pill ${health ? "pill-ok" : "pill-warn"}`}>
            {health ? `API ONLINE v${health.version}` : "API OFFLINE"}
          </span>
          <button type="button" className="btn-ghost" onClick={() => void refreshAll()}>
            Refresh
          </button>
        </div>
      </header>

      {error && <div className="banner-error">{error}</div>}

      <section className="metrics">
        <article className="metric-card">
          <span>Learnings Stored</span>
          <strong>{health?.stats.learnings ?? 0}</strong>
        </article>
        <article className="metric-card">
          <span>Honest Reports</span>
          <strong>{health?.stats.reports ?? 0}</strong>
        </article>
        <article className="metric-card">
          <span>Adaptations Logged</span>
          <strong>{health?.stats.adaptations ?? 0}</strong>
        </article>
      </section>

      <nav className="tabs">
        {(
          [
            ["learn", "Knowledge Base"],
            ["reports", "Honest Reports"],
            ["adaptations", "Adaptations"],
            ["safety", "Charter & Safety"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`tab ${tab === key ? "tab-active" : ""}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "learn" && (
        <section className="grid-two">
          <form className="panel" onSubmit={(e) => void handleLearnSubmit(e)}>
            <h2>Record New Learning</h2>
            <label>
              Topic
              <input
                value={learnTopic}
                onChange={(e) => setLearnTopic(e.target.value)}
                placeholder="e.g., Cloud VM Environment"
                required
              />
            </label>
            <label>
              Verified Insight
              <textarea
                rows={4}
                value={learnContent}
                onChange={(e) => setLearnContent(e.target.value)}
                placeholder="What did Lazarus discover or verify?"
                required
              />
            </label>
            <label>
              Tags (comma-separated)
              <input
                value={learnTags}
                onChange={(e) => setLearnTags(e.target.value)}
                placeholder="python, infra, research"
              />
            </label>
            <button type="submit" className="btn-primary">
              Save Learning
            </button>
          </form>

          <div className="panel">
            <div className="panel-head">
              <h2>Recall Memory</h2>
              <input
                className="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter learnings..."
              />
            </div>
            <ul className="feed">
              {learnings.length === 0 && <li className="muted">No learnings recorded yet.</li>}
              {learnings.map((item) => (
                <li key={item.id} className="feed-item">
                  <div className="feed-title">
                    <strong>{item.topic}</strong>
                    <span className="timestamp">{item.created_at}</span>
                  </div>
                  <p>{item.content}</p>
                  {item.tags.length > 0 && (
                    <div className="tags">
                      {item.tags.map((tag) => (
                        <span key={tag} className="tag">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {tab === "reports" && (
        <section className="grid-two">
          <form className="panel" onSubmit={(e) => void handleReportSubmit(e)}>
            <h2>Log Honest Report</h2>
            <label>
              Title
              <input
                value={reportTitle}
                onChange={(e) => setReportTitle(e.target.value)}
                placeholder="e.g., Daily System Intelligence"
                required
              />
            </label>
            <label>
              Verified Findings
              <textarea
                rows={4}
                value={reportSummary}
                onChange={(e) => setReportSummary(e.target.value)}
                placeholder="Summarize verified facts transparently..."
                required
              />
            </label>
            <label>
              Honest Gaps / Uncertainties
              <textarea
                rows={2}
                value={reportGaps}
                onChange={(e) => setReportGaps(e.target.value)}
                placeholder="Explicitly state what is not yet verified or still uncertain"
              />
            </label>
            <label>
              Confidence: {formatConfidence(reportConfidence)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={reportConfidence}
                onChange={(e) => setReportConfidence(Number(e.target.value))}
              />
            </label>
            <button type="submit" className="btn-primary">
              Publish Report
            </button>
          </form>

          <div className="panel">
            <h2>Recent Reports</h2>
            <ul className="feed">
              {reports.length === 0 && <li className="muted">No reports filed yet.</li>}
              {reports.map((rep) => (
                <li key={rep.id} className="feed-item">
                  <div className="feed-title">
                    <strong>{rep.title}</strong>
                    <span className="pill pill-ok">{formatConfidence(rep.confidence)}</span>
                  </div>
                  <p>{rep.summary}</p>
                  {rep.honest_gaps && (
                    <p className="gap-note">
                      <strong>Honest Gaps:</strong> {rep.honest_gaps}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {tab === "adaptations" && (
        <section className="grid-two">
          <form className="panel" onSubmit={(e) => void handleAdaptSubmit(e)}>
            <h2>Record Adaptation</h2>
            <label>
              Trigger (What changed?)
              <input
                value={adaptTrigger}
                onChange={(e) => setAdaptTrigger(e.target.value)}
                placeholder="e.g., New API version or tool discovered"
                required
              />
            </label>
            <label>
              Adaptation Made
              <textarea
                rows={3}
                value={adaptChange}
                onChange={(e) => setAdaptChange(e.target.value)}
                placeholder="How Lazarus adapted its workflow or tooling"
                required
              />
            </label>
            <label>
              Rationale
              <textarea
                rows={2}
                value={adaptRationale}
                onChange={(e) => setAdaptRationale(e.target.value)}
                placeholder="Why this adaptation makes Lazarus stronger"
                required
              />
            </label>
            <button type="submit" className="btn-primary">
              Log Adaptation
            </button>
          </form>

          <div className="panel">
            <h2>Adaptation History</h2>
            <ul className="feed">
              {adaptations.length === 0 && <li className="muted">No adaptations recorded yet.</li>}
              {adaptations.map((item) => (
                <li key={item.id} className="feed-item">
                  <div className="feed-title">
                    <strong>{item.trigger}</strong>
                    <span className="timestamp">{item.created_at}</span>
                  </div>
                  <p>{item.change}</p>
                  <p className="muted">Rationale: {item.rationale}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {tab === "safety" && (
        <section className="grid-two">
          <div className="panel">
            <h2>Lazarus Core Charter</h2>
            <ul className="feed">
              {(constitution?.directives ?? []).map((dir) => (
                <li key={dir.id} className="feed-item">
                  <div className="feed-title">
                    <strong>{dir.title}</strong>
                    <span className={`tag tag-${dir.category}`}>{dir.category.toUpperCase()}</span>
                  </div>
                  <p>{dir.description}</p>
                </li>
              ))}
            </ul>
          </div>

          <form className="panel" onSubmit={(e) => void handleSafetyCheck(e)}>
            <h2>Non-Harm Guardrail Simulator</h2>
            <label>
              Proposed Command or Action
              <textarea
                rows={4}
                value={actionToCheck}
                onChange={(e) => setActionToCheck(e.target.value)}
                placeholder="Test any command or action against Lazarus safety rules..."
                required
              />
            </label>
            <button type="submit" className="btn-primary">
              Evaluate Safety
            </button>

            {evaluation && (
              <div className={`eval-box eval-${evaluation.risk_level}`}>
                <strong>{riskBadgeLabel(evaluation.risk_level)}</strong>
                <p>{evaluation.reason}</p>
                <p className="muted">{evaluation.note}</p>
              </div>
            )}
          </form>
        </section>
      )}
    </div>
  );
}
