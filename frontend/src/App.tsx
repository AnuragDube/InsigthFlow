import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { Dataset, Page } from "./api/types";
import { Data } from "./pages/Data";
import { Overview } from "./pages/Overview";
import { Questions } from "./pages/Questions";

type Tab = "overview" | "data" | "questions";
function tabFromHash(): Tab {
  const hash = window.location.hash;
  if (hash === "#data") return "data";
  return hash === "#questions" ? "questions" : "overview";
}

function pickDefault(items: Dataset[]): Dataset | undefined {
  // Most recently published first; otherwise the newest dataset.
  return [...items].sort((a, b) => {
    if (Boolean(a.published_run_id) !== Boolean(b.published_run_id)) return a.published_run_id ? -1 : 1;
    return b.created_at.localeCompare(a.created_at);
  })[0];
}

function Welcome({ onReady }: { onReady: (id: string, tab: Tab) => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: async (withSample: boolean) => {
      const ds = await api.createDataset(withSample ? "Sample shop (UCI Online Retail II)" : "My shop");
      if (withSample) await api.loadSample(ds.id);
      return ds;
    },
    onSuccess: (ds) => {
      void qc.invalidateQueries({ queryKey: ["datasets"] });
      onReady(ds.id, "data");
    },
    onError: (e: Error) => setError(e.message),
  });
  return (
    <section className="empty">
      <h1 className="summary">See what your shop’s orders say, with every number checked.</h1>
      <p>
        Load sample orders or upload your own order lines. Each upload is cleaned and checked before it appears in
        the dashboard.
      </p>
      {error && <p className="notice error">{error}</p>}
      <div className="actions">
        <button type="button" className="btn" disabled={start.isPending} onClick={() => start.mutate(true)}>
          {start.isPending ? "Setting up…" : "Load sample data"}
        </button>
        <button type="button" className="btn quiet" disabled={start.isPending} onClick={() => start.mutate(false)}>
          Upload your own CSV
        </button>
      </div>
    </section>
  );
}

export function App() {
  const qc = useQueryClient();
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [chosen, setChosen] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: api.createDataset,
    onSuccess: (dataset) => {
      qc.setQueryData<Page<Dataset>>(["datasets"], (previous) => ({
        items: [...(previous?.items ?? []), dataset],
      }));
      setChosen(dataset.id);
      setName("");
      setCreating(false);
    },
  });

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = (t: Tab) => {
    window.location.hash = t === "overview" ? "" : t;
    setTab(t);
  };

  const items = datasets.data?.items ?? [];
  const current = items.find((d) => d.id === chosen) ?? pickDefault(items);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          Insight<span>Flow</span>
        </div>
        {current && (
          <>
            <nav className="tabs" aria-label="Sections">
              <button type="button" className="tab" aria-current={tab === "overview" ? "page" : undefined} onClick={() => go("overview")}>
                Overview
              </button>
              <button type="button" className="tab" aria-current={tab === "data" ? "page" : undefined} onClick={() => go("data")}>
                Data
              </button>
              <button type="button" className="tab" aria-current={tab === "questions" ? "page" : undefined} onClick={() => go("questions")}>
                Ask
              </button>
            </nav>
            {items.length > 1 && (
              <label className="field">
                Dataset
                <select value={current.id} onChange={(e) => setChosen(e.target.value)}>
                  {items.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </>
        )}
      </header>
      <main>
        {datasets.error && <p className="notice error">Can’t reach the API: {datasets.error.message}</p>}
        {datasets.isLoading && <p className="hint">Loading…</p>}
        {datasets.data && !current && (
          <Welcome
            onReady={(id, t) => {
              setChosen(id);
              go(t);
            }}
          />
        )}
        {current && tab === "overview" && <Overview key={current.id} datasetId={current.id} onOpenData={() => go("data")} />}
        {current && tab === "questions" && <Questions key={current.id} datasetId={current.id} />}
        {current && tab === "data" && (
          <>
            {creating ? (
              <form
                className="toolbar"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (name.trim() && !create.isPending) create.mutate(name.trim());
                }}
              >
                <label className="field">
                  Dataset name
                  <input type="text" required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} />
                </label>
                <button type="submit" className="btn" disabled={create.isPending || !name.trim()}>
                  Create dataset
                </button>
                <button
                  type="button"
                  className="btn quiet"
                  disabled={create.isPending}
                  onClick={() => {
                    create.reset();
                    setName("");
                    setCreating(false);
                  }}
                >
                  Cancel
                </button>
                {create.error && <p className="notice error" role="alert">{create.error.message}</p>}
              </form>
            ) : (
              <div className="toolbar">
                <button type="button" className="btn quiet" onClick={() => setCreating(true)}>
                  New dataset
                </button>
              </div>
            )}
            <Data key={current.id} datasetId={current.id} />
          </>
        )}
      </main>
    </div>
  );
}
