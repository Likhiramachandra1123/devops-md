# RegView — Strict RAG Assistant with Pluggable Ingestion

Ask questions in natural language against your own private knowledge base. RegView
retrieves the most relevant chunks from a local vector store, then asks Claude to
write a short, cited answer — and **refuses** to answer if the knowledge base
doesn't cover the question (no hallucinations from Claude's training data).

**Stack:** FastAPI + Anthropic Claude + ChromaDB + PubMedBERT embeddings + Angular 18.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [First-time setup](#2-first-time-setup)
3. [Configure `.env`](#3-configure-env)
4. [Start the backend](#4-start-the-backend)
5. [Start the frontend](#5-start-the-frontend)
6. [Ingest your data](#6-ingest-your-data)
7. [Verify everything works](#7-verify-everything-works)
8. [Common tasks](#8-common-tasks)
9. [Troubleshooting](#9-troubleshooting)
10. [Project layout](#10-project-layout)

---

## 1. Prerequisites

Install these **before** you start. Verify each one from a fresh terminal.

| Tool | Version | Verify command | Get it from |
|---|---|---|---|
| **Python** | 3.11.x | `python --version` | https://www.python.org/downloads/ (tick "Add Python to PATH") |
| **Node.js + npm** | Node 20 LTS | `node --version` `npm --version` | https://nodejs.org/ |
| **Git** *(optional)* | any | `git --version` | https://git-scm.com/download/win |
| **Anthropic API key** | — | — | https://console.anthropic.com/ → *API Keys* → *Create Key* |

**Optional — only needed if you plan to ingest from those sources:**

| Source | Extra install |
|---|---|
| MySQL / MariaDB | `pip install pymysql` |
| PostgreSQL | `pip install "psycopg[binary]"` |
| MongoDB | `pip install pymongo` |
| Amazon S3 / MinIO / R2 | `pip install boto3` |

---

## 2. First-time setup

Open a terminal in the project root. Both shells work — pick one.

### 2a. Open the project folder

**PowerShell**
```powershell
cd C:\Users\LikhithR\Documents\Hackcellerate
```

**CMD**
```cmd
cd /d C:\Users\LikhithR\Documents\Hackcellerate
```

### 2b. Create a virtual environment

**PowerShell / CMD** (same command)
```
python -m venv .venv
```

### 2c. Activate the virtual environment

**PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

> If PowerShell blocks the script with an execution-policy error, run once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

**CMD**
```cmd
.venv\Scripts\activate.bat
```

Your prompt should now show `(.venv)` at the start.

### 2d. Install Python dependencies

```
pip install --upgrade pip
pip install -r requirements.txt
```

First run downloads PyTorch + the PubMedBERT embedding model (~500 MB). Takes a few minutes; only happens once.

### 2e. Install frontend dependencies

```
cd frontend
npm install
cd ..
```

---

## 3. Configure `.env`

Copy the template and open it for editing:

**PowerShell**
```powershell
Copy-Item .env.example .env
notepad .env
```

**CMD**
```cmd
copy .env.example .env
notepad .env
```

Set at minimum:

```env
ANTHROPIC_API_KEY=sk-ant-your-real-key-here
```

Everything else has sensible defaults. Notable knobs:

| Setting | Default | Meaning |
|---|---|---|
| `CLAUDE_MODEL` | `claude-3-5-haiku-latest` | Default model. Users can switch per-request via the UI picker. |
| `RAG_DISTANCE_THRESHOLD` | `0.55` | Cosine distance — chunks farther than this are discarded. Lower = stricter. |
| `RAG_TOP_DISTANCE_FLOOR` | `0.45` | Even after threshold-filtering, the best chunk must be within this. Extra safety net. |
| `RAG_STRICT` | `true` | If retrieval finds nothing, refuse to answer instead of guessing from Claude's memory. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Chunker window in characters. |
| `UPLOAD_MAX_DOC_CHARS` | `400000` | Max chars sent to Claude in a `/chat/upload` call. |

> **Any `.env` change requires a backend restart** (settings are cached at process start).

---

## 4. Start the backend

Keep the venv activated. From the project root:

```
uvicorn app.main:create_app --factory --port 8000
```

Wait for:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

**API docs** are live at http://localhost:8000/docs (Swagger UI).
**Health check:** http://localhost:8000/health

Leave this terminal running.

---

## 5. Start the frontend

Open a **second** terminal (leave the backend running).

```
cd C:\Users\LikhithR\Documents\Hackcellerate\frontend
npm start
```

First launch prints a URL like `http://localhost:4200/`. Open it in Chrome or Edge (voice typing needs Web Speech API, which is Chromium-only).

The frontend proxies `/api/*` to the backend on port 8000 via [proxy.conf.json](frontend/proxy.conf.json) — no CORS setup needed.

---

## 6. Ingest your data

RegView answers **only** from what's in ChromaDB. Empty store = every question gets refused. Pick the ingestion path that matches your data source.

### 6a. Databases (MySQL, Postgres, SQLite, MongoDB, S3) — recommended path

Everything goes through **one script**: [scripts/ingest_mysql_all.py](scripts/ingest_mysql_all.py) for MySQL/MariaDB (and, with the connection URL adapted, any SQL database SQLAlchemy supports).

For **any other source** (Mongo, S3, other SQL) use the same `/ingest/source` API — the script wraps it, and you can also POST payloads directly.

#### MySQL example (auto-discovers text-bearing tables)

Open a third terminal (leave backend + frontend running):

**PowerShell**
```powershell
cd C:\Users\LikhithR\Documents\Hackcellerate
.\.venv\Scripts\Activate.ps1
python scripts\ingest_mysql_all.py `
  --url "mysql+pymysql://USER:PASS@HOST:3306/DBNAME" `
  --dry-run
```

**CMD**
```cmd
cd /d C:\Users\LikhithR\Documents\Hackcellerate
.venv\Scripts\activate.bat
python scripts\ingest_mysql_all.py ^
  --url "mysql+pymysql://USER:PASS@HOST:3306/DBNAME" ^
  --dry-run
```

`--dry-run` prints the plan (which tables, which columns) without writing anything. Review it, then re-run **without** `--dry-run`:

**PowerShell**
```powershell
python scripts\ingest_mysql_all.py `
  --url "mysql+pymysql://USER:PASS@HOST:3306/DBNAME" `
  --max-per-table 500
```

**CMD**
```cmd
python scripts\ingest_mysql_all.py ^
  --url "mysql+pymysql://USER:PASS@HOST:3306/DBNAME" ^
  --max-per-table 500
```

#### Script flags

| Flag | Default | Meaning |
|---|---|---|
| `--url` | *(required)* | SQLAlchemy connection URL. See [connection URL cookbook](#connection-url-cookbook) below. |
| `--dry-run` | off | Print the ingest plan; do nothing. |
| `--max-per-table` | 500 | Cap rows ingested per table. Start small, scale up once quality looks good. |
| `--min-rows` | 1 | Skip tables with fewer rows than this. |
| `--max-rows` | 200000 | Skip tables larger than this (safety brake). |
| `--only` | *(none)* | Comma-separated table names — ingest only these, bypasses the auto-skip list. |
| `--wide-text-only` | off | Only ingest tables with real prose columns. Default: ingest everything so ID/status/date lookups also work. |
| `--api-url` | `http://localhost:8000/ingest/source` | Change if the backend runs elsewhere. |

#### What it auto-does per table

- Picks the primary key as the record ID
- Picks a title column (`title` / `name` / `subject` / `label` / …)
- Every non-secret column becomes filterable metadata
- Short scalars (ids, statuses, dates) are prepended to the embedded text so ID/status lookups work via vector search
- Skips secrets by name (`password`, `token`, `secret`, `hash`, `salt`, `signature`) and binary types (`BLOB`, `VARBINARY`)
- Skips obvious junk tables (audit logs, sessions, `sequelizemeta`, pure mapping tables, etc.) — override with `--only`

#### Connection URL cookbook

| DB | URL scheme | Install |
|---|---|---|
| MySQL / MariaDB | `mysql+pymysql://user:pass@host:3306/db` | `pip install pymysql` |
| PostgreSQL | `postgresql+psycopg://user:pass@host:5432/db` | `pip install "psycopg[binary]"` |
| SQLite | `sqlite:///./path/to/file.db` | *(built in)* |
| SQL Server | `mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server` | `pip install pyodbc` |
| Oracle | `oracle+oracledb://user:pass@host:1521/?service_name=XEPDB1` | `pip install oracledb` |

For **MongoDB** and **S3**, call the API directly (see [API examples](#api-examples-mongo-and-s3) below).

### 6b. Local files (PDF, DOCX, TXT, MD, HTML)

Two options:

**Interactive one-off** — use the "Attach file" button in the chat UI. The file is sent to `/chat/upload`, chunked, and answered against a single question.

**Bulk folder ingest** — drop files into `data/documents/` and run:

```
python scripts\ingest_documents.py
```

### 6c. URLs

```
python scripts\ingest_urls.py --file scripts\seed_urls.txt
```

Or POST directly:

```powershell
Invoke-RestMethod http://localhost:8000/ingest/url -Method Post `
  -ContentType "application/json" `
  -Body '{"url":"https://example.com/some-article"}'
```

### 6d. One-shot: URLs + local docs + FDA / ClinicalTrials connectors

`scripts/ingest_all.py` is the fastest way to seed a demo knowledge base. It calls, in order:

1. Every URL in the seed file (`scripts/seed_urls.txt` by default).
2. Every supported file (`.pdf`, `.docx`, `.txt`, `.md`, `.html`) under a docs folder (`data/documents/` by default).
3. Per drug in `--drugs`: openFDA drug labels, FAERS adverse events, Orange Book patents/exclusivity, drug enforcement actions.
4. Per condition in `--conditions`: ClinicalTrials.gov studies.
5. Per device term in `--devices`: 510(k) records and device enforcement actions.

Failures in one connector never abort the run — each source is logged and the pipeline moves on.

**PowerShell — defaults**
```powershell
cd C:\Users\LikhithR\Documents\Hackcellerate
.\.venv\Scripts\Activate.ps1
python -m scripts.ingest_all
```

**PowerShell — custom terms**
```powershell
python -m scripts.ingest_all `
  --urls scripts\seed_urls.txt `
  --docs .\data\documents `
  --drugs "atorvastatin,metformin,ibuprofen" `
  --conditions "hypertension,type 2 diabetes" `
  --devices "insulin pump,pacemaker" `
  --limit 25
```

**CMD**
```cmd
python -m scripts.ingest_all ^
  --drugs "atorvastatin,metformin,ibuprofen" ^
  --conditions "hypertension,type 2 diabetes" ^
  --devices "insulin pump,pacemaker" ^
  --limit 25
```

#### Script flags

| Flag | Default | Meaning |
|---|---|---|
| `--urls` | `scripts/seed_urls.txt` | Seed URL file (one URL per line, `#` starts a comment). Pass an empty string to skip. |
| `--docs` | `data/documents` | Folder to bulk-ingest local files from. Pass an empty string to skip. |
| `--drugs` | `atorvastatin,metformin,ibuprofen` | Comma-separated drug names for labels / FAERS / Orange Book / drug enforcement. |
| `--conditions` | `hypercholesterolemia,type 2 diabetes,hypertension` | Comma-separated conditions for ClinicalTrials.gov. |
| `--devices` | `insulin pump,pacemaker` | Comma-separated device terms for 510(k) and device enforcement. |
| `--limit` | `25` | Per-connector record cap (FAERS uses `limit × 2`). |

The backend does **not** need to be running for this script — it writes directly to the local ChromaDB and session store. Only an outbound internet connection to `api.fda.gov`, `clinicaltrials.gov`, and (for URL ingest) the seed sites is required.

### API examples (Mongo and S3)

Both hit `POST /ingest/source` — the same endpoint the MySQL script uses.

**MongoDB**
```powershell
$body = @{
  type = "mongo"
  max_records = 1000
  config = @{
    connection_url = "mongodb://user:pass@localhost:27017"
    database = "mydb"
    collection = "articles"
    title_field = "title"
    text_fields = @("summary", "body")
    id_field = "_id"
    source_label = "mongo_articles"
  }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod http://localhost:8000/ingest/source -Method Post `
  -ContentType "application/json" -Body $body
```

**S3 / MinIO / R2**
```powershell
$body = @{
  type = "s3"
  max_records = 200
  config = @{
    bucket = "my-docs"
    prefix = "reports/2026/"
    region_name = "us-east-1"
    extensions = @(".pdf", ".docx", ".txt")
    source_label = "s3_reports"
  }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod http://localhost:8000/ingest/source -Method Post `
  -ContentType "application/json" -Body $body
```

For MinIO/R2 add `endpoint_url`, `aws_access_key_id`, `aws_secret_access_key` to the `config` block.

---

## 7. Verify everything works

**Backend health**
```powershell
Invoke-RestMethod http://localhost:8000/health
```

**How many chunks are in the vector store**
```powershell
Invoke-RestMethod http://localhost:8000/ingest/stats
```

**Available Claude models** (live-fetched from Anthropic + local pricing)
```powershell
Invoke-RestMethod http://localhost:8000/models
```

**Ask a test question**
```powershell
$body = @{ message = "What's in the knowledge base?"; use_rag = $true } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/chat -Method Post `
  -ContentType "application/json" -Body $body
```

Or just open the UI at http://localhost:4200/ and type a question.

---

## 8. Common tasks

### Change which model the UI defaults to
Edit `CLAUDE_MODEL` in `.env`, restart the backend. Users can still switch per-request via the picker in the top-right of the chat header.

### Wipe the vector store and start fresh

**PowerShell**
```powershell
# Ctrl+C the backend first
Remove-Item -Recurse -Force .\data\chroma
```

**CMD**
```cmd
rmdir /s /q data\chroma
```

Restart the backend — the collection is recreated empty on startup.

### Delete a single document from Chroma
```powershell
Invoke-RestMethod "http://localhost:8000/ingest/documents/DOC_ID_HERE" -Method Delete
```
Doc IDs are returned in the ingest response and shown in citations.

### Make refusals stricter (fewer off-topic answers)
In `.env`:
```env
RAG_DISTANCE_THRESHOLD=0.40
RAG_TOP_DISTANCE_FLOOR=0.30
```
Restart backend.

### Make retrieval more permissive (more matches, more noise)
```env
RAG_DISTANCE_THRESHOLD=0.70
RAG_TOP_DISTANCE_FLOOR=0.60
```

### Voice typing
Click the mic icon in the composer. Chrome / Edge only (uses Web Speech API). Speak, then click again to stop — the transcript is appended to the text box in real time.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `python: command not found` | Python isn't in PATH. Reinstall from python.org with "Add Python to PATH" ticked. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once. |
| `ModuleNotFoundError: pymysql` (or `pymongo`, `boto3`) | Install the driver: `pip install pymysql` (etc.). Optional deps aren't bundled. |
| `Access denied for user 'root'@'localhost'` | MySQL user/password in the URL is wrong. Verify with `mysql -u root -p`. |
| `Can't connect to MySQL server on 'localhost:3306'` | MySQL isn't running, or firewall blocks it. Start the service. |
| `Address already in use` on port 8000 | Something else is on 8000. Find it: `Get-NetTCPConnection -LocalPort 8000 \| Select OwningProcess`, then `Stop-Process -Id <pid>`. Or start uvicorn with `--port 8001`. |
| Frontend shows "cannot reach API" | Backend isn't running, or on a different port. Check http://localhost:8000/health. |
| `ConnectionError` from the ingest script | Backend isn't running. Start `uvicorn app.main:create_app --factory --port 8000` first. |
| Every question gets refused ("I don't have information…") | Vector store is empty (`/ingest/stats` says 0 chunks) OR the query genuinely doesn't match anything ingested. Loosen thresholds or ingest more data. |
| Claude answers questions clearly outside your data | You either turned `RAG_STRICT=false`, or the retrieval threshold is too loose. Tighten `RAG_TOP_DISTANCE_FLOOR`. |
| "temperature is deprecated by the model" | Some Claude 4 preview models reject custom sampling params. Switch to a stable model in the picker, or lower `CLAUDE_TEMPERATURE` to `1.0`. |
| Model list in UI is empty / stale | Backend can't reach Anthropic. Check `/models` — if it says `"source": "static"`, the API call failed (bad key, no network). |
| `.env` change had no effect | Restart the backend — settings are cached at process start. |

---

## 10. Project layout

```
Hackcellerate/
├── app/                        FastAPI backend
│   ├── main.py                 App factory + router registration
│   ├── config.py               .env-driven settings
│   ├── api/                    HTTP endpoints
│   │   ├── chat.py             /chat, /chat/upload, /chat/search
│   │   ├── ingest.py           /ingest/*  (files, URLs, /ingest/source for DBs)
│   │   └── models.py           /models  (Claude model catalog + pricing)
│   ├── core/                   Claude client, embeddings, retriever, prompts
│   ├── db/                     Session store (SQLite via aiosqlite)
│   ├── ingestion/              Chunker, loaders (pdf/docx/html/txt), source connectors
│   │   └── sources/            base.py, sql.py, mongo.py, s3.py, registry.py
│   └── models/                 Pydantic request/response schemas
├── frontend/                   Angular 18 SPA
│   ├── src/app/components/     chat, composer, model-picker, split-layout, …
│   ├── src/app/services/       api.service.ts
│   └── proxy.conf.json         /api → http://127.0.0.1:8000
├── scripts/
│   ├── ingest_mysql_all.py     ★ recommended DB ingestion script
│   ├── ingest_documents.py     Bulk-ingest files from data/documents/
│   ├── ingest_urls.py          Ingest URLs from a text file
│   └── demo.py                 End-to-end smoke test
├── data/
│   ├── chroma/                 ChromaDB persistent store (created on first run)
│   ├── documents/              Drop PDFs/DOCX/TXT here for scripts/ingest_documents.py
│   └── sessions.db             SQLite conversation history
├── requirements.txt
├── .env.example                Template — copy to .env, add ANTHROPIC_API_KEY
└── README.md                   This file
```

---

## Quick reference — all four terminals you'll typically open

| # | Purpose | Command |
|---|---|---|
| 1 | Backend (long-running) | `uvicorn app.main:create_app --factory --port 8000` |
| 2 | Frontend (long-running) | `cd frontend; npm start` |
| 3 | Ingestion / API testing | `python scripts\ingest_mysql_all.py --url "..." --dry-run` |
| 4 | *(optional)* MySQL client / Python REPL | `mysql -u root -p` |

Backend must be running before you invoke any ingestion script — they POST to the running API.
