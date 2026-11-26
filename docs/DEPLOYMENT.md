# InsightFlow — Deployment Design & Free-Tier Feasibility

Status: Draft for approval (Phase 1) · Research date: 2026-11-24

## 1. How these facts were gathered (read first)
Facts below come from official vendor documentation/pricing/terms, gathered via web search restricted to
vendor domains; direct page fetches were blocked by this dev environment's network policy. Items marked
**UNVERIFIED** could not be confirmed and must be checked on the live page **before** relying on them.
Free tiers change frequently — re-verify at the time of each deployment and update this file.

## 2. Strategy in one paragraph
**The interview demo runs locally** (most reliable: no cold starts, no quotas except Groq), with a recorded
screen capture as a fallback and an offline demo mode for the AI features. A **public demo** is optional
and **read-only and stateless**: bundled sample data is processed at build/start time, uploads are
disabled, so ephemeral disks and sleeping instances do not lose anything. Persistent, multi-user hosting
waits for P1 (auth) and uses a free Postgres (Neon) for metadata. **No free tier below is suitable for paying
customers**; commercial launch requires paid infrastructure (§6). A public demo never exposes an
unrestricted quota-consuming AI endpoint: either the labelled offline (fake) provider, or live AI behind a
small global daily budget. Only public/synthetic data is used in any public demo. No hosting decision is
final; terms are re-verified before any deployment, and deployment requires owner approval.

## 3. Environments

| Environment | Frontend | Backend | Metadata DB | Analytical storage | LLM |
|---|---|---|---|---|---|
| Local dev (Windows) | Vite dev server | `uvicorn` on 127.0.0.1 | SQLite file | local `data/` | Groq free or `fake` |
| Tests/CI | — / Playwright | in-process | SQLite (P0), + Postgres service container (P1) | temp dir | `fake` only |
| Public read-only demo (optional) | static build (Cloudflare Pages or Netlify) | free container host (Render or Koyeb) | SQLite in image (read-only demo needs no shared state) | Gold built at image build from bundled sample | Groq, strict rate limit |
| Private beta (P1) | same | same | Neon free Postgres | object storage (Backblaze B2 free 10 GB) or rebuilt-on-start | Groq |

## 4. Service facts

### Groq (LLM)
- OpenAI-compatible API, base URL `https://api.groq.com/openai/v1` (console.groq.com/docs/openai).
- A $0 Free tier exists (console.groq.com/docs/billing-faqs). **Per-model free RPM/RPD/TPM/TPD: UNVERIFIED**
  — check console.groq.com/docs/rate-limits and your org's *Settings → Limits* page and record them here.
- **Card required for free tier: UNVERIFIED.** **Commercial use on free tier: UNVERIFIED.**
- Model churn: `llama-3.3-70b-versatile` shut down 2026-08-16; suggested replacements include
  `openai/gpt-oss-120b` and `qwen/qwen3.6-27b` (console.groq.com/docs/deprecations). ⇒ model id is config.
- Data: Groq states it does not retain inference inputs/outputs by default except for limited
  reliability/abuse cases; Zero Data Retention can be enabled (console.groq.com/docs/your-data).
- This dev container currently blocks `api.groq.com`; enabling it is requested when the AI phase starts.

### Backend hosting
| Service | Free offering | Sleep | Disk | Card | Commercial | Verdict |
|---|---|---|---|---|---|---|
| Render | Free web service; 750 instance-hours/workspace/month | Spins down after 15 min idle; ~1 min wake | Ephemeral | Marketing says no card; staff report possible card verification ($1 reversed) — **treat as possibly required** | UNVERIFIED | Candidate for read-only demo |
| Koyeb | 1 free instance: 512 MB RAM, 0.1 vCPU, 2 GB SSD, Frankfurt/Washington | Scale-to-zero after 1 h idle | No volumes | **UNVERIFIED** | "not for production" | Candidate; 512 MB is tight — must measure memory |
| Hugging Face Spaces | **Docker/Gradio Spaces on free CPU now require PRO** (HTTP 402 without) | 48 h | Ephemeral | — | — | ✗ Not free for our backend anymore |
| Fly.io | 7-day $1 trial; ongoing free plan **requires a card** | — | Volumes | Required | — | ✗ Violates no-card rule |
| Streamlit Cloud | 2.7 GB RAM; sleeps after 12 h | — | — | — | — | ✗ Wrong stack (React+FastAPI) |

### Frontend hosting
| Service | Notes | Commercial |
|---|---|---|
| Cloudflare Pages | 500 builds/month, 20k files/site, 25 MiB/file | No restriction found in limits docs (verify ToS) |
| Netlify Free | 300 credits/month, hard cap, pauses instead of billing | Commercial use allowed per Netlify |
| Vercel Hobby | Generous limits | **Non-commercial only**; Hobby content may be used to train AI ✗ for commercial path |
| GitHub Pages | 100 GB/month soft | **Prohibits SaaS/commercial-transaction sites** ✗ for commercial path |

### Databases & storage
| Service | Free offering | Persistence/sleep | Card |
|---|---|---|---|
| Neon Postgres | Up to 100 projects; 100 CU-hours/project/month; 1 GB storage/project | Scale-to-zero after 5 min (cold start on next query); over quota → compute suspended, data kept | Not required |
| Supabase | 500 MB DB, 1 GB files, 2 active projects | Paused after ~1 week of low activity; restorable 90 days | Free: UNVERIFIED |
| Render Postgres | 1 GB | **Expires 30 days** after creation (+14-day grace, then deleted) ✗ | — |
| Backblaze B2 | First 10 GB free | Persistent | Not required to start |
| Cloudflare R2 | 10 GB-month, 1M Class A / 10M Class B ops | Persistent | **Conflicting sources — may require a payment method** ⚠ flag before use |

### CI and Databricks
- GitHub Actions: standard runners free & unlimited for **public** repos; private repos on GitHub Free get
  $12/month of compute credit (≈2,000 Linux minutes, our estimate). ⇒ keep CI lean; public repo is free.
- Databricks Free Edition: serverless only, one 2X-Small SQL warehouse, 5 concurrent job tasks, daily
  quota (compute shuts down for the day when exceeded, data kept), Unity Catalog enabled, file upload to
  Volumes + `spark.read.csv`, **no card**, **not for commercial use**, no SLA. Delta support implied by Unity
  Catalog tables but not explicitly verified. ⇒ suitable for the P1 demonstration path only.

## 5. Constraints that shape the design
1. **Cold starts** (Render ~1 min, Neon few seconds): the frontend shows a "waking the demo server" state;
   never demo live from a sleeping free host — use local.
2. **Ephemeral disks**: public demo is stateless by construction; private beta needs B2 (or Neon for small
   docs) for anything that must persist.
3. **Memory**: measured peak ≈ 1.0 GB RSS for a full UCI pipeline run (DATA_PROFILE.md), 153 MB idle.
   A 512 MB instance (Koyeb) does not fit as-is; a read-only demo that only *serves* prebuilt Gold
   may — to be measured. DuckDB `memory_limit` is configurable.
4. **Quotas pause rather than bill** on Netlify/Vercel/Neon — good for ₹0, bad for availability.
5. **Non-commercial terms**: Databricks Free Edition, Vercel Hobby, GitHub Pages — never on the commercial path.
6. **Card-required services** are excluded: Fly.io; R2 and Render are flagged until verified.

## 6. What cannot be safely deployed for free (production requirements)
- Real customer data with uploads: needs authenticated, persistent, backed-up storage with an SLA.
- Multi-tenant SaaS: needs always-on compute (no 1-minute cold starts), managed Postgres with backups/PITR,
  shared rate-limit store, background workers, monitoring/alerting, incident response.
- Contractual data processing with the LLM provider (DPA, retention guarantees) — free-tier terms are not a
  basis for customer commitments.
Indicative production stack later (paid, not chosen now): managed container platform, managed Postgres,
object storage, a contracted LLM provider. Revisit costs when there is revenue validation.

## 7. Operational notes

### Workspace upload quotas

Set `INSIGHTFLOW_MAX_WORKSPACE_UPLOAD_MB` to cap retained CSV bytes per workspace in MiB.
The default is 5,120 MiB. Files count while stored, including deactivated batches, because
Bronze retains their raw copies. Uploading identical bytes again to the same dataset reuses
the stored batch. A quota rejection leaves the published run intact. This quota tracks raw
CSV bytes. Budget disk space separately for transient uploads, Parquet, DuckDB, and backups.

### SQLite workspace backup and restore

Let running pipeline work finish, then stop InsightFlow before copying the workspace. The
backup combines the SQLite metadata with the file warehouse, so both must stay stable during
the copy. Run these commands from the repository root with the application's
`INSIGHTFLOW_DATABASE_URL` and `INSIGHTFLOW_DATA_DIR` settings.

```powershell
uv run --frozen python scripts/backup_workspace.py backup ./workspace-backup
uv run --frozen python scripts/backup_workspace.py restore ./workspace-backup ./restored-workspace
```

Choose new directories outside the source workspace data directory. Keep backups private
because they include uploaded data, documents, and database records. An interrupted backup
is usable only if it has a complete manifest and passes verification.
Restored users sign in again. The backup copy omits browser sessions.

To test the restored copy without changing the original, set separate paths before starting
the application:

```powershell
$restore = (Resolve-Path ./restored-workspace).Path.Replace('\', '/')
$env:INSIGHTFLOW_DATA_DIR = "$restore/data"
$env:INSIGHTFLOW_DATABASE_URL = "sqlite:///$restore/metadata.sqlite3"
```

Start the app and check readiness, open a published dashboard, and confirm that expected
documents are present. Restore verifies SHA-256 file hashes and SQLite integrity and refuses to
overwrite an existing directory. The command expects a trusted SQLite backup and a single
stopped instance. Keep the original workspace until the restored copy has been inspected.
- Secrets set only in host dashboards; never in images or repo. Rotate Groq key if exposed: revoke in console,
  update host env, redeploy.
- `PUBLIC_DEMO_MODE=read_only` is required for any public URL in P0 (enforced at startup: app refuses to bind
  `0.0.0.0` without it unless `ALLOW_PUBLIC_WRITE=true` *and* auth is enabled — P1).
- Health: `/health` (liveness), `/ready` (DB + storage). Free hosts' health checks hit `/health`.
