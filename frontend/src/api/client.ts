import type { Dashboard, Dataset, Ingestion, Page, QualityResult, Run, RunRequest, Upload } from "./types";

/** Error carrying the server's RFC 9457 problem details. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly type: string,
    readonly detail: string,
  ) {
    super(detail);
  }
}

// Mutations must carry this header: the API's CSRF guard rejects cross-site requests without it.
const CLIENT_HEADER = { "X-InsightFlow-Client": "web" };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const mutating = init.method && init.method !== "GET";
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { ...(mutating ? CLIENT_HEADER : {}), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let type = "/errors/http";
    let detail = `Request failed (${res.status}).`;
    try {
      const body = (await res.json()) as { type?: string; detail?: string };
      type = body.type ?? type;
      detail = body.detail ?? detail;
    } catch {
      /* not JSON: keep the generic message */
    }
    throw new ApiError(res.status, type, detail);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  datasets: () => request<Page<Dataset>>("/datasets"),
  createDataset: (name: string) => request<Dataset>("/datasets", json({ name })),
  ingestions: (id: string) => request<Page<Ingestion>>(`/datasets/${id}/ingestions`),
  upload: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Upload>(`/datasets/${id}/uploads`, { method: "POST", body: form });
  },
  loadSample: (id: string) => request<RunRequest>(`/datasets/${id}/load-sample`, { method: "POST" }),
  rebuild: (id: string) => request<RunRequest>(`/datasets/${id}/pipeline-runs`, { method: "POST" }),
  setBatchActive: (id: string, ingestionId: string, isActive: boolean) =>
    request<RunRequest>(`/datasets/${id}/ingestions/${ingestionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: isActive }),
    }),
  runs: (id: string) => request<Page<Run>>(`/pipeline-runs?dataset_id=${encodeURIComponent(id)}`),
  run: (runId: string) => request<Run>(`/pipeline-runs/${runId}`),
  quality: (runId: string) => request<Page<QualityResult>>(`/pipeline-runs/${runId}/quality`),
  dashboard: (id: string, from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    const qs = q.toString();
    return request<Dashboard>(`/datasets/${id}/dashboard${qs ? `?${qs}` : ""}`);
  },
};
