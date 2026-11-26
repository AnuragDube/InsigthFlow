import { useCurrency } from "../lib/currency";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { formatDateRange, formatValue } from "../lib/format";

const EXAMPLES = [
  "How much did we sell?",
  "How many orders did we have?",
  "What was the average order value?",
];

export function Questions({ datasetId }: { datasetId: string }) {
  const currency = useCurrency();
  const [question, setQuestion] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const ask = useMutation({
    mutationFn: () => api.ask(datasetId, question.trim(), from || undefined, to || undefined),
  });
  const answer = ask.data;

  return (
    <>
      <h1 className="summary">Ask about your metrics.</h1>
      <p className="hint">Ask about a dashboard metric. Use the date fields or add “from YYYY-MM-DD to YYYY-MM-DD” to your question.</p>
      <div className="toolbar" aria-label="Example questions">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" className="chip" onClick={() => setQuestion(example)}>
            {example}
          </button>
        ))}
      </div>
      <form className="toolbar" onSubmit={(event) => {
        event.preventDefault();
        if (question.trim() && !ask.isPending) ask.mutate();
      }}>
        <label className="field question-field">
          Question
          <input type="text" value={question} maxLength={240} required onChange={(event) => setQuestion(event.target.value)} />
        </label>
        <label className="field">
          From
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="field">
          To
          <input type="date" value={to} min={from || undefined} onChange={(event) => setTo(event.target.value)} />
        </label>
        <button type="submit" className="btn" disabled={!question.trim() || ask.isPending}>
          {ask.isPending ? "Checking…" : "Ask question"}
        </button>
      </form>
      {ask.error && <p className="notice error" role="alert">{ask.error.message}</p>}
      {answer && (
        <section className="section" aria-live="polite">
          <h2>{answer.label}: {answer.value === null ? "No value for this period" : formatValue(answer.value, answer.unit, currency)}</h2>
          <p>{answer.description}</p>
          <p className="hint">{formatDateRange(answer.from, answer.to)}</p>
          <details>
            <summary>Query and published run</summary>
            {currency.code !== "GBP" && <p className="hint">The query returns monetary values in GBP.</p>}
            <p className="hint">Run {answer.run_id}</p>
            {answer.sql.map((statement, index) => <pre className="query-sql" key={index}>{statement}</pre>)}
            <p className="hint">Bound dates: {answer.parameters.start} inclusive to {answer.parameters.end} exclusive.</p>
          </details>
        </section>
      )}
    </>
  );
}
