import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, api } from "./api/client";
import type { Dataset, Page } from "./api/types";
import { Customers } from "./pages/Customers";
import { Data } from "./pages/Data";
import { Documents } from "./pages/Documents";
import { Forecast } from "./pages/Forecast";
import { Overview } from "./pages/Overview";
import { Questions } from "./pages/Questions";

type Tab = "overview" | "data" | "questions" | "documents" | "forecast" | "customers";
function tabFromHash(): Tab {
  const hash = window.location.hash;
  if (hash === "#data") return "data";
  if (hash === "#customers") return "customers";
  if (hash === "#forecast") return "forecast";
  if (hash === "#documents") return "documents";
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
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: api.datasets,
    retry: (count, error) =>
      count < 3 && !(error instanceof ApiError && [401, 403].includes(error.status)),
  });
  const session = useQuery({ queryKey: ["session-options"], queryFn: api.sessionOptions });
  const signOut = useMutation({
    mutationFn: api.signOut,
    onSuccess: () => window.location.assign("/"),
  });
  const signInRequired =
    session.data?.interactive && datasets.error instanceof ApiError && datasets.error.status === 401;
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

  if (signInRequired) {
    return (
      <main className="shell">
        <h1 className="summary">Sign in to InsightFlow.</h1>
        <form className="toolbar" onSubmit={(event) => {
          event.preventDefault();
          const workspace = String(new FormData(event.currentTarget).get("workspace") ?? "");
          const params = new URLSearchParams({ workspace });
          window.location.assign(`/api/v1/session/login?${params}`);
        }}>
          <label className="field question-field">
            Workspace ID
            <input
              type="text"
              name="workspace"
              required
              pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
              maxLength={36}
            />
          </label>
          <button className="btn" type="submit">Continue to sign in</button>
        </form>
      </main>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          Insight<span>Flow</span>
        </div>
        <nav className="tabs" aria-label="Sections">
          {current ? (
            <>
              <button type="button" className="tab" aria-current={tab === "overview" ? "page" : undefined} onClick={() => go("overview")}>
                Overview
              </button>
              <button type="button" className="tab" aria-current={tab === "data" ? "page" : undefined} onClick={() => go("data")}>
                Data
              </button>
              <button type="button" className="tab" aria-current={tab === "questions" ? "page" : undefined} onClick={() => go("questions")}>
                Ask
              </button>
              <button type="button" className="tab" aria-current={tab === "forecast" ? "page" : undefined} onClick={() => go("forecast")}>
                Forecast
              </button>
              <button type="button" className="tab" aria-current={tab === "customers" ? "page" : undefined} onClick={() => go("customers")}>
                Customers
              </button>
            </>
          ) : (
            <button type="button" className="tab" aria-current={tab !== "documents" ? "page" : undefined} onClick={() => go("overview")}>
              Home
            </button>
          )}
          <button type="button" className="tab" aria-current={tab === "documents" ? "page" : undefined} onClick={() => go("documents")}>
            Documents
          </button>
        </nav>
        {current && tab !== "documents" && items.length > 1 && (
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
        {session.data?.interactive && datasets.isSuccess && (
          <button className="btn quiet" type="button" disabled={signOut.isPending} onClick={() => signOut.mutate()}>
            Sign out
          </button>
        )}
      </header>
      <main>
        {signOut.error && <p className="notice error" role="alert">{signOut.error.message}</p>}
        {datasets.error && <p className="notice error">Can’t reach the API: {datasets.error.message}</p>}
        {datasets.isLoading && <p className="hint">Loading…</p>}
        {datasets.data && !current && tab !== "documents" && (
          <Welcome
            onReady={(id, t) => {
              setChosen(id);
              go(t);
            }}
          />
        )}
        {tab === "documents" && <Documents />}
        {current && tab === "overview" && <Overview key={current.id} datasetId={current.id} onOpenData={() => go("data")} />}
        {current && tab === "customers" && <Customers key={current.id} datasetId={current.id} runId={current.published_run_id} />}
        {current && tab === "forecast" && <Forecast key={current.id} datasetId={current.id} runId={current.published_run_id} />}
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
