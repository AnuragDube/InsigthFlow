import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";

export function Documents() {
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const documents = useQuery({ queryKey: ["documents"], queryFn: api.documents });
  const search = useMutation({ mutationFn: api.searchDocuments });
  const refresh = () => {
    search.reset();
    return qc.invalidateQueries({ queryKey: ["documents"] });
  };
  const upload = useMutation({ mutationFn: api.uploadDocument, onSuccess: refresh });
  const remove = useMutation({
    mutationFn: api.deleteDocument,
    onSuccess: async () => {
      setPendingDelete(null);
      await refresh();
    },
  });
  const changesPending = upload.isPending || remove.isPending;
  const error = documents.error ?? upload.error ?? remove.error ?? search.error;

  return (
    <>
      <h1 className="summary">Search your documents.</h1>
      <form className="toolbar" onSubmit={(event) => {
        event.preventDefault();
        if (question.trim() && !search.isPending && !changesPending) search.mutate(question.trim());
      }}>
        <label className="field question-field">
          Search question
          <input type="text" maxLength={240} value={question} onChange={(event) => setQuestion(event.target.value)} />
        </label>
        <button className="btn" type="submit" disabled={!question.trim() || search.isPending || changesPending}>
          {search.isPending ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p className="notice error" role="alert">{error.message}</p>}
      {search.data && (
        <section className="section" aria-live="polite">
          <h2>Matching excerpts</h2>
          {search.data.length === 0 && <p>No matching evidence was found.</p>}
          {search.data.map((match, index) => (
            <article key={match.document_id + index}>
              <h3>{match.title} · {match.start_line === match.end_line ? "Line" : "Lines"} {match.start_line}{match.end_line > match.start_line ? `–${match.end_line}` : ""}</h3>
              <blockquote className="query-sql">{match.excerpt}</blockquote>
            </article>
          ))}
        </section>
      )}
      <section className="section">
        <h2>Document library</h2>
        <label className="field">
          Upload document
          <input
            type="file"
            accept=".txt,.md"
            disabled={changesPending || search.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) upload.mutate(file);
              event.target.value = "";
            }}
          />
        </label>
        <p className="hint">UTF-8 text or Markdown, up to 64 KiB per file.</p>
        {upload.isPending && <p role="status">Uploading…</p>}
        {documents.isPending && <p role="status">Loading documents…</p>}
        {documents.data?.length === 0 && <p className="hint">No documents uploaded.</p>}
        {documents.data?.map((doc) => (
          <div className="toolbar" key={doc.id}>
            <span>{doc.title}</span>
            {pendingDelete === doc.id ? (
              <>
                <button className="btn" type="button" disabled={changesPending || search.isPending} onClick={() => remove.mutate(doc.id)}>Confirm removal</button>
                <button className="btn quiet" type="button" disabled={remove.isPending} onClick={() => setPendingDelete(null)}>Cancel</button>
              </>
            ) : (
              <button className="btn quiet" type="button" disabled={changesPending} onClick={() => setPendingDelete(doc.id)} aria-label={`Remove ${doc.title}`}>Remove</button>
            )}
          </div>
        ))}
      </section>
    </>
  );
}
