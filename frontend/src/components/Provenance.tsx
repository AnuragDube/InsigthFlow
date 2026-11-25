import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Dashboard } from "../api/types";
import { formatValue } from "../lib/format";

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Where the numbers came from: rows read, kept, counted, and the quality verdict. */
export function Provenance({ freshness, onOpenData }: { freshness: Dashboard["freshness"]; onOpenData: () => void }) {
  const run = useQuery({
    queryKey: ["run", freshness.run_id],
    queryFn: () => api.run(freshness.run_id as string),
    enabled: Boolean(freshness.run_id),
  });
  const silver = run.data?.stages.find((s) => s.stage === "silver");
  const gold = run.data?.stages.find((s) => s.stage === "gold");
  const q = freshness.quality;
  const total = q.passed + q.warnings + q.failed;
  return (
    <p className="provenance">
      {silver && gold && (
        <>
          <b>{formatValue(silver.rows_in, "count")}</b> lines read, <b>{formatValue(silver.rows_out, "count")}</b>{" "}
          kept after cleaning, <b>{formatValue(gold.rows_out, "count")}</b> counted as sales.{" "}
        </>
      )}
      <span className={`badge ${q.failed ? "bad" : q.warnings ? "warn" : "ok"}`}>
        {q.passed} of {total} quality checks passed
      </span>{" "}
      {q.warnings > 0 && `(${q.warnings} warning${q.warnings > 1 ? "s" : ""}) `}
      Published {when(freshness.finished_at)}.{" "}
      <button type="button" className="linkish" onClick={onOpenData}>
        See the data and checks
      </button>
    </p>
  );
}
