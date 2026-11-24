import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../api/client";
import type { QualityResult, Run, RunStatus } from "../api/types";
import { formatDuration, formatValue } from "../lib/format";

const STATUS_TEXT: Record<RunStatus, string> = {
  queued: "Waiting to start",
  running: "Running",
  succeeded: "Published",
  failed: "Failed",
  blocked_by_quality: "Blocked by quality checks",
};
const STATUS_BADGE: Record<RunStatus, string> = {
  queued: "warn", running: "warn", succeeded: "ok", failed: "bad", blocked_by_quality: "bad",
};
const ACTIVE = new Set<RunStatus>(["queued", "running"]);

function when(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function observed(q: QualityResult): string {
  if (q.observed === null) return "no data";
  const ratio = q.threshold !== null && q.threshold <= 1 && q.observed <= 1 && !Number.isInteger(q.observed);
  return ratio ? `${(q.observed * 100).toFixed(2)}%` : formatValue(q.observed, "count");
}

function runDuration(r: Run): number | null {
  const total = r.stages.reduce((s, st) => s + (st.duration_ms ?? 0), 0);
  return r.stages.length ? total : null;
}

export function Data({ datasetId }: { datasetId: string }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const batches = useQuery({ queryKey: ["ingestions", datasetId], queryFn: () => api.ingestions(datasetId) });
  const runs = useQuery({
    queryKey: ["runs", datasetId],
    queryFn: () => api.runs(datasetId),
    // Poll only while something is queued or running.
    refetchInterval: (q) => (q.state.data?.items.some((r) => ACTIVE.has(r.status)) ? 1500 : false),
  });
  const runId = selected ?? runs.data?.items[0]?.id ?? null;
  const runStatus = runs.data?.items.find((r) => r.id === runId)?.status;
  const quality = useQuery({
    // Status is part of the key: results fetched while a run was still queued are empty and must
    // not be reused once it finishes (found by the e2e test).
    queryKey: ["quality", runId, runStatus],
    queryFn: () => api.quality(runId as string),
    enabled: Boolean(runId),
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["ingestions", datasetId] });
    void qc.invalidateQueries({ queryKey: ["runs", datasetId] });
    void qc.invalidateQueries({ queryKey: ["dashboard", datasetId] });
    void qc.invalidateQueries({ queryKey: ["datasets"] });
    setSelected(null);
  };
  const onError = (e: Error) => setMessage({ kind: "error", text: e.message });

  const upload = useMutation({
    mutationFn: (file: File) => api.upload(datasetId, file),
    onSuccess: (r) => {
      setMessage({
        kind: "ok",
        text: r.created
          ? `Uploaded ${r.ingestion.original_name} (${formatValue(r.ingestion.row_count, "count")} lines). Processing started.`
          : `${r.ingestion.original_name} was already uploaded; nothing changed.`,
      });
      refresh();
    },
    onError,
  });
  const sample = useMutation({
    mutationFn: () => api.loadSample(datasetId),
    onSuccess: () => {
      setMessage({ kind: "ok", text: "Sample data loaded. Processing started." });
      refresh();
    },
    onError,
  });
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => api.setBatchActive(datasetId, id, active),
    onSuccess: () => {
      setMessage({ kind: "ok", text: "Batch updated. Rebuilding the dashboard data." });
      refresh();
    },
    onError,
  });

  return (
    <>
      <h1 className="summary">Your data, and how it was checked.</h1>
      {message && (
        <p className={`notice${message.kind === "error" ? " error" : ""}`} role="status">
          {message.text}
        </p>
      )}

      <section className="section">
        <h2>Add data</h2>
        <p className="hint">
          CSV with columns Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country. Each
          upload is kept unchanged; lines repeated across uploads are counted once.
        </p>
        <div className="toolbar">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            aria-label="CSV file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate(f);
              e.target.value = "";
            }}
            hidden
          />
          <button type="button" className="btn" disabled={upload.isPending} onClick={() => fileRef.current?.click()}>
            {upload.isPending ? "Uploading…" : "Upload CSV"}
          </button>
          <button type="button" className="btn quiet" disabled={sample.isPending} onClick={() => sample.mutate()}>
            {sample.isPending ? "Loading…" : "Load sample data"}
          </button>
        </div>
      </section>

      <section className="section">
        <h2>Uploads</h2>
        <p className="hint">Excluding an upload rebuilds the dashboard without it. The file itself is kept.</p>
        {batches.data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th className="num">Lines</th>
                  <th>Uploaded</th>
                  <th>In use</th>
                </tr>
              </thead>
              <tbody>
                {batches.data.items.map((b) => (
                  <tr key={b.id}>
                    <td>{b.original_name}</td>
                    <td className="num">{formatValue(b.row_count, "count")}</td>
                    <td>{when(b.created_at)}</td>
                    <td>
                      {b.is_active ? "Yes" : "Excluded"}{" "}
                      <button
                        type="button"
                        className="linkish"
                        disabled={toggle.isPending}
                        aria-label={`${b.is_active ? "Exclude" : "Include"} ${b.original_name}`}
                        onClick={() => toggle.mutate({ id: b.id, active: !b.is_active })}
                      >
                        {b.is_active ? "Exclude" : "Include"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint">No uploads yet.</p>
        )}
      </section>

      <section className="section">
        <h2>Processing runs</h2>
        <p className="hint">Each run rebuilds the dashboard from all included uploads. A blocked run never replaces published data.</p>
        {runs.data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Reason</th>
                  <th>Result</th>
                  <th className="num">Lines read</th>
                  <th className="num">Quarantined</th>
                  <th className="num">Time</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.items.map((r) => {
                  const silver = r.stages.find((s) => s.stage === "silver");
                  return (
                    <tr key={r.id} aria-selected={r.id === runId}>
                      <td>
                        <button type="button" className="linkish" onClick={() => setSelected(r.id)}>
                          {when(r.started_at ?? r.created_at)}
                        </button>
                      </td>
                      <td>{r.trigger}</td>
                      <td>
                        <span className={`badge ${STATUS_BADGE[r.status]}`}>{STATUS_TEXT[r.status]}</span>
                      </td>
                      <td className="num">{formatValue(silver?.rows_in ?? null, "count")}</td>
                      <td className="num">{formatValue(silver?.rows_quarantined ?? null, "count")}</td>
                      <td className="num">{formatDuration(runDuration(r))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint">No runs yet. Upload a file or load the sample data.</p>
        )}
      </section>

      {runId && (
        <section className="section">
          <h2>Quality checks for the selected run</h2>
          <p className="hint">Blocking checks must pass before data is published; warnings are reported only.</p>
          {quality.data?.items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Kind</th>
                    <th className="num">Observed</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {quality.data.items.map((q) => (
                    <tr key={`${q.stage}-${q.rule_id}`}>
                      <td>{q.description}</td>
                      <td>{q.severity === "blocking" ? "Blocking" : "Warning"}</td>
                      <td className="num">{observed(q)}</td>
                      <td>
                        <span className={`badge ${q.passed ? "ok" : q.severity === "blocking" ? "bad" : "warn"}`}>
                          {q.passed ? "Passed" : "Failed"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="hint">This run stopped before its checks ran.</p>
          )}
        </section>
      )}
    </>
  );
}
