# RegView — Your AI Regulatory Search Assistant

**In one sentence:** You type a question about FDA drugs, clinical trials, or patents. RegView searches your own documents first, then asks Claude (an AI) to write a short answer with source links.

This guide walks you through everything — even if you've never run a Python project before.

---

## Table of contents

1. [What does it do?](#1-what-does-it-do)
2. [What you need before starting](#2-what-you-need-before-starting)
3. [Step-by-step: get it running on your laptop](#3-step-by-step-get-it-running-on-your-laptop)
4. [Step-by-step: add documents so it can answer smartly](#4-step-by-step-add-documents-so-it-can-answer-smartly)
5. [Step-by-step: test everything (copy-paste commands)](#5-step-by-step-test-everything-copy-paste-commands)
6. [How to connect a website / frontend](#6-how-to-connect-a-website--frontend)
7. [Fixing common problems](#7-fixing-common-problems)
8. [What each folder does](#8-what-each-folder-does)
9. [Going to production](#9-going-to-production)

---

## 1. What does it do?

Imagine a helpful librarian who has already read:

- All FDA drug labels
- All reported side effects (FAERS)
- All clinical trials on ClinicalTrials.gov
- The Orange Book (patents & exclusivity)
- Any PDFs / Word docs / web pages you give it

You ask the librarian a plain-English question like:

> *"What are the approved uses of atorvastatin, and when does its patent expire?"*

The librarian:

1. **Looks in the library** (your documents) for the 3 most relevant snippets.
2. **Hands those snippets to Claude** (Anthropic's AI) as reference.
3. **Claude writes a 3–4 line summary** and cites the sources like `[1] [2] [3]`.
4. **Remembers your last 50 questions** so you can ask follow-ups naturally.

If nothing relevant is in the library, Claude just answers from its own general knowledge and clearly tells you it did so.

---

## 2. What you need before starting

Install these three things first.

| Tool | Why we need it | Where to get it |
|---|---|---|
| **Python 3.11** | Runs the backend | https://www.python.org/downloads/ (pick 3.11.x) |
| **Git** *(optional)* | Only if cloning from a repo | https://git-scm.com/download/win |
| **An Anthropic API key** | Lets us talk to Claude | https://console.anthropic.com/ → *API Keys* → *Create Key* |

> **Important:** When installing Python on Windows, **tick the "Add Python to PATH" checkbox** on the first installer screen. If you forget, uninstall and reinstall.

### Verify the install

Open PowerShell (press `Win` → type `PowerShell` → Enter) and run:

```powershell
python --version
```

You should see `Python 3.11.x`. If you see an error, Python isn't installed correctly.

---

## 3. Step-by-step: get it running on your laptop

### Step 3.1 — Open the project folder

```powershell
cd C:\Users\LikhithR\Documents\Hackcellerate
```

### Step 3.2 — Create a "virtual environment"

Think of this as a private sandbox for the project's Python packages so it doesn't affect your system.

```powershell
python -m venv .venv
```

A new folder called `.venv` appears.

### Step 3.3 — Turn on the sandbox

> **Use PowerShell**, not Command Prompt (cmd). To open PowerShell: press `Win` → type `PowerShell` → Enter. This whole guide uses PowerShell commands.
>
> If you accidentally use Command Prompt (cmd), running `Activate.ps1` will just **open the file in Notepad** — that's the symptom that tells you you're in the wrong terminal.

**In PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

If you get an error like *"execution of scripts is disabled"*, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**If you must use Command Prompt (cmd)** instead:

```cmd
.venv\Scripts\activate.bat
```

Either way, when it worked, you'll see `(.venv)` in front of your prompt:

```
(.venv) PS C:\Users\LikhithR\Documents\Hackcellerate>
```

### Step 3.4 — Install all the required packages

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> Use `python -m pip install --upgrade pip` (not `pip install --upgrade pip`) on Windows — otherwise pip complains it can't overwrite itself while it's running. If you see that message, this is the fix. You can also skip the upgrade entirely; it's optional.

This downloads FastAPI, Claude's SDK, the PubMedBERT AI model tools, ChromaDB (the search database), and more. Takes **5–10 minutes** the first time.

### Step 3.5 — Set up your secret key

Copy the example config file:

```powershell
copy .env.example .env
```

Now open the new `.env` file in Notepad (or VS Code) and change **one line**:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Replace `sk-ant-your-key-here` with the actual key from https://console.anthropic.com/. **Save the file.**

> Keep this file private. Never share it or push it to Git — `.gitignore` already excludes it.

### Step 3.6 — Start the server

```powershell
uvicorn app.main:app --reload --port 8000
```

You'll see logs ending with something like:

```
INFO: Uvicorn running on http://0.0.0.0:8000
INFO: Startup complete.
```

That's it — **your backend is running**. First launch downloads the PubMedBERT AI model (~440 MB), so give it 1–2 minutes.

### Step 3.7 — Open the built-in test page

Open your browser and go to:

**http://localhost:8000/docs**

You'll see a colorful page called **Swagger UI** — a built-in playground where you can try every endpoint without writing code.

Leave the terminal running. To stop the server, press `Ctrl+C` in that terminal.

---

## 4. Step-by-step: add documents so it can answer smartly

Right now the library is empty. The AI will still answer, but only from Claude's own general knowledge. Let's fill it up.

You have **three ways** to add content — do any (or all) in any order.

### Option 0 — The one-command "ingest everything" (recommended first)

Runs the URL seed list, any files in `data\documents`, and all connectors (drug labels + FAERS + Orange Book + drug enforcement + ClinicalTrials + 510(k) + device enforcement) in a single go:

```powershell
python -m scripts.ingest_all
```

Defaults pull data for a few starter drugs (`atorvastatin`, `metformin`, `ibuprofen`), conditions (`hypercholesterolemia`, `type 2 diabetes`, `hypertension`), and devices (`insulin pump`, `pacemaker`). Customise:

```powershell
python -m scripts.ingest_all `
    --urls scripts\seed_urls.txt `
    --docs .\data\documents `
    --drugs "atorvastatin,metformin,paracetamol" `
    --conditions "psoriasis,hypertension" `
    --devices "insulin pump,defibrillator" `
    --limit 30
```

Individual pieces (below) are still there if you want fine control.

### Option 0b — The "index EVERYTHING" bulk ingest

If you want the widest possible coverage so the AI can cite local sources for
just about any FDA-regulated product / trial:

```powershell
python -m scripts.ingest_bulk
```

What it pulls:

- **openFDA drug labels** — up to 25,000 (API cap)
- **FDA Orange Book** — every product (~34k rows), patents + exclusivity
- **openFDA 510(k) device clearances** — up to 25,000
- **openFDA enforcement / recalls** — up to 25,000 each for drug / device / food
- **ClinicalTrials.gov** — capped at `--trials-limit` (default 5000; set higher or use `--trials-query cancer` to focus)
- **Every URL in** `scripts\seed_urls.txt`
- **FAERS bulk is intentionally skipped** (millions of raw events — not useful as vectors). Use `ingest_sources --source openfda-faers --query "<drug>"` for the per-drug summary.

Useful flags:

```powershell
python -m scripts.ingest_bulk --labels-max 5000 --trials-limit 20000
python -m scripts.ingest_bulk --only orangebook,labels
python -m scripts.ingest_bulk --skip clinicaltrials,510k
```

Expect this to take a while (network + embeddings) and use a few GB of disk
under `data\chroma\`. It's fully **idempotent** — running it again just
re-checks; existing documents aren't duplicated.

**How the "local first, Claude fallback" works** (this is already wired up, no
config needed):

1. Every question first hits the local ChromaDB library.
2. If any chunks pass the similarity threshold (`RAG_DISTANCE_THRESHOLD` in `.env`), the answer is grounded — you'll see `"grounded": true` and `citations` in the API response.
3. If nothing local matches, the response is `"grounded": false` and Claude answers from its own general knowledge, with the reply prefixed by *"Not found in the internal knowledge base — answering from general knowledge:"* so users always know the source.

### Option A — Pull real FDA data automatically

Open a **second** PowerShell window (leave the server running in the first).

```powershell
cd C:\Users\LikhithR\Documents\Hackcellerate
.\.venv\Scripts\Activate.ps1
```

Now pull data for a drug you care about. Example — **atorvastatin** (Lipitor):

**FDA drug labels** (approved uses, warnings, dosing):
```powershell
python -m scripts.ingest_sources --source openfda-labels --query "atorvastatin" --limit 25
```

**Reported side effects (FAERS):**
```powershell
python -m scripts.ingest_sources --source faers --query "atorvastatin" --limit 100
```

**Related clinical trials:**
```powershell
python -m scripts.ingest_sources --source clinicaltrials --query "hypercholesterolemia" --limit 30
```

**Patent & exclusivity (Orange Book):**
```powershell
python -m scripts.ingest_sources --source orangebook --query "atorvastatin" --limit 50
```

**Medical device 510(k) clearances:**
```powershell
python -m scripts.ingest_sources --source device-510k --query "insulin pump" --limit 30
```

**Drug/device/food recalls (enforcement):**
```powershell
python -m scripts.ingest_sources --source drug-enforcement   --query "contamination" --limit 50
python -m scripts.ingest_sources --source device-enforcement --query "pacemaker"     --limit 50
python -m scripts.ingest_sources --source food-enforcement   --query "salmonella"    --limit 50
```

Each command prints how many chunks were added. Repeat for any drug or condition — just change `--query`.

### Option B — Upload your own PDFs, Word docs, or web pages

**B.1 — PDFs / DOCX / TXT / HTML files**

1. Put the files into the `data\documents` folder (sub-folders are fine).
2. Run:

```powershell
python -m scripts.ingest_documents --path .\data\documents --source internal --tags "guidance,sop"
```

Supported formats: **PDF, DOCX, TXT, MD, HTML**.

**B.2 — A list of web URLs**

1. Create a file `my_urls.txt` inside `scripts\`. One URL per line:

```
https://www.fda.gov/drugs/development-approval-process-drugs
https://open.fda.gov/apis/
# lines starting with # are comments
```

2. Run:

```powershell
python -m scripts.ingest_urls --file scripts\my_urls.txt --source web
```

A ready-made starter file `scripts\seed_urls.txt` is included — you can use it directly.

> **Kaggle datasets** (`kaggle.com/datasets/...`) require login to download the actual CSV. If you ingest a Kaggle URL directly, RegView only captures the page description — not the rows. To get the real data:
> 1. Click **Download** on the Kaggle page.
> 2. Unzip the CSVs into `data\documents\kaggle\`.
> 3. Run `python -m scripts.ingest_documents --path .\data\documents\kaggle --source kaggle`.

### Option C — Add stuff from the browser (no CLI)

Go to http://localhost:8000/docs, expand any endpoint under `ingest` or `sources`, click **"Try it out"**, fill in the fields, and hit **Execute**. Same result as the commands above.

### Check what's in the library

```powershell
curl http://localhost:8000/ingest/stats
```

Output like `{"chunk_count": 2437}` — that's the number of searchable pieces in your library.

---

## 5. Step-by-step: test everything (copy-paste commands)

Keep the server running.

### Test 5.1 — Is the server alive?

Open a second PowerShell window and run:

```powershell
curl http://localhost:8000/health
```

Expected:
```json
{"status":"ok","version":"1.0.0","model":"claude-sonnet-4-5-20250929","embedding_model":"pritamdeka/S-PubMedBert-MS-MARCO","vector_store_count":2437}
```

If `vector_store_count` is `0`, go back to Section 4 and add some documents.

### Test 5.2 — Ask your first question (creates a new conversation)

```powershell
curl -X POST http://localhost:8000/chat `
     -H "Content-Type: application/json" `
     -d '{"message": "What are the approved uses of atorvastatin?"}'
```

Response JSON includes:

- `session_id` — **save this string**; you'll need it for follow-ups
- `answer` — full response with citations `[1] [2]`
- `summary` — the short 3–4 line version
- `citations` — source snippets with URLs
- `grounded: true` — found relevant docs in your library
- `grounded: false` — fell back to Claude's own knowledge

### Test 5.3 — Follow-up in the same conversation

Reuse the `session_id`:

```powershell
curl -X POST http://localhost:8000/chat `
     -H "Content-Type: application/json" `
     -d '{"session_id": "PASTE-YOUR-SESSION-ID-HERE", "message": "And what are its most common side effects?"}'
```

The AI remembers previous turns. You can keep going for **at least 50 messages** per session.

### Test 5.4 — See the whole conversation

```powershell
curl http://localhost:8000/sessions/PASTE-YOUR-SESSION-ID-HERE/messages
```

### Test 5.5 — List all conversations

```powershell
curl http://localhost:8000/sessions
```

### Test 5.6 — Do it visually (recommended)

Everything above is easier through the browser:

1. Go to **http://localhost:8000/docs**
2. Expand **POST /chat** → click **"Try it out"**
3. Type your question in the JSON body → click **"Execute"**
4. Copy the `session_id` from the response → paste it back for the next question

### Test 5.7 — One-command end-to-end smoke test (fastest way to verify everything)

Runs the whole pipeline (ingest → retrieve → Claude → citations) in a single command and prints every step:

```powershell
python -m scripts.demo
```

You'll see the ingestion progress, the top retrieved chunks with distances, and Claude's final answer with sources — all in one terminal window. Perfect for sanity-checking after a fresh install.

**Useful flags:**

```powershell
# Custom drug + question
python -m scripts.demo --drug "metformin" --question "What are metformin's contraindications?"

# Skip Claude — only test retrieval (no API key needed, no cost)
python -m scripts.demo --no-claude

# Skip ingestion — reuse whatever's already in Chroma
python -m scripts.demo --skip-ingest --question "your question"
```

---

## 6. How to connect a website / frontend

Minimum JavaScript needed to call RegView from any web page:

```html
<script>
async function askRegView(question) {
  const savedSessionId = localStorage.getItem("regview_session");

  const response = await fetch("http://localhost:8000/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: savedSessionId,   // null on first call
      message: question,
      use_rag: true                  // set false to skip the library and only use Claude
    })
  });

  const data = await response.json();
  localStorage.setItem("regview_session", data.session_id);   // remember for next time

  console.log("Summary:", data.summary);
  console.log("Full answer:", data.answer);
  console.log("Sources:", data.citations);
  return data;
}

askRegView("What are the approved uses of atorvastatin?");
</script>
```

**Cross-origin note:** websites at `http://localhost:3000` (React) or `http://localhost:5173` (Vite) are already allowed. To allow other origins, edit `CORS_ORIGINS` in `.env` (comma-separated list) and restart the server.

---

## 7. Fixing common problems

### "To modify pip, please run … python.exe -m pip install --upgrade pip"
Not an error — Windows can't let pip overwrite itself while running. Run it through Python instead:
```powershell
python -m pip install --upgrade pip
```
Or skip the upgrade entirely and go straight to `pip install -r requirements.txt`.

### "Activate.ps1 just opened Notepad and nothing happened"
You're in **Command Prompt (cmd)**, not PowerShell. `.ps1` files only run in PowerShell. Either:
- Open **PowerShell** (`Win` → type `PowerShell` → Enter) and re-run `.\.venv\Scripts\Activate.ps1`, **or**
- Stay in cmd and run `.venv\Scripts\activate.bat` instead.

### "python is not recognized"
You didn't tick "Add Python to PATH" when installing. Reinstall Python and tick the box.

### "cannot be loaded because running scripts is disabled"
Run this in PowerShell once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### "ANTHROPIC_API_KEY … validation error"
You didn't set the key in `.env`, or the file is missing. Copy `.env.example` → `.env`, paste your key from https://console.anthropic.com/, save.

### "Port 8000 is already in use"
Another program is using port 8000. Use a different one:
```powershell
uvicorn app.main:app --reload --port 8080
```
Then use `http://localhost:8080` everywhere.

### First `/chat` call takes 30–60 seconds
Normal on the very first call — PubMedBERT is loading into memory. Later calls are fast.

### `grounded: false` on every question
Your library is empty. Add documents (Section 4).

### Answers cite irrelevant snippets
The AI is being too generous. In `.env` lower `RAG_DISTANCE_THRESHOLD` from `0.55` to `0.45`. Restart the server. Lower = stricter matches only.

### Answers say "not found" when the info IS in your docs
Being too strict. Raise `RAG_DISTANCE_THRESHOLD` to `0.65` and restart.

### Ingesting a huge PDF eats all memory
Reduce `CHUNK_SIZE` to `500` in `.env` and re-ingest.

---

## 8. What each folder does

```
Hackcellerate/
├── app/                    ← the backend code
│   ├── main.py              ← starts the FastAPI server
│   ├── config.py            ← reads settings from .env
│   ├── api/                 ← the URL endpoints (chat, sessions, ingest, sources)
│   ├── core/                ← the "brain" (Claude, embeddings, search, memory)
│   ├── db/                  ← saves conversations to SQLite
│   ├── ingestion/           ← reads PDFs/URLs and puts them in the library
│   │   └── connectors/      ← FDA, FAERS, ClinicalTrials, Orange Book downloaders
│   └── models/              ← shapes of API requests/responses
├── scripts/                ← command-line tools to bulk-load documents
├── data/                   ← everything the app saves lives here
│   ├── chroma/              ← the vector search library (auto-created)
│   ├── documents/           ← drop your PDFs/DOCX here
│   └── sessions.db          ← your saved conversations
├── .env                    ← YOUR settings and secret key (never share!)
├── .env.example            ← template for .env
├── requirements.txt        ← list of Python packages
├── Dockerfile              ← for running in a container
├── docker-compose.yml      ← one-command docker startup
└── README.md               ← this file
```

### Tuning knobs in `.env` (plain-English)

| Setting | What it means |
|---|---|
| `CLAUDE_MODEL` | Which Claude version to use. Sonnet is a good default. |
| `CLAUDE_MAX_TOKENS` | Max answer length (1500 ≈ ~1000 words). |
| `CLAUDE_TEMPERATURE` | How creative Claude gets. `0` = strict, `1` = imaginative. `0.2` is right for regulatory. |
| `CHUNK_SIZE` | Size of each library snippet (in characters). |
| `CHUNK_OVERLAP` | How much neighboring snippets overlap so nothing gets cut mid-sentence. |
| `RAG_TOP_K` | How many candidate snippets to look at per question. |
| `RAG_FINAL_K` | How many of those to actually send to Claude. |
| `RAG_DISTANCE_THRESHOLD` | Match-quality cutoff. **Lower = stricter**. |
| `MAX_HISTORY_MESSAGES` | How many past messages to remember per conversation (50 by default). |

---

## 9. Going to production

When you're ready to expose this to real users, do these (in order):

1. **Put it behind HTTPS** — use Nginx, Cloudflare Tunnel, or a cloud load balancer.
2. **Add authentication** — this API is currently open to anyone who can reach it. Add an OAuth2 proxy, API gateway, or API-key middleware.
3. **Add rate limiting** — protect your Claude spend using `slowapi` or gateway-level limits.
4. **Swap SQLite for Postgres** — change `SESSION_DB_URL` in `.env` to a Postgres URL (no code changes needed).
5. **Swap ChromaDB for a hosted vector DB** (Qdrant, Weaviate, Pinecone) once you have >1M chunks or need multi-server support.
6. **Run in Docker** for reproducibility:

   ```powershell
   docker compose up --build
   ```

7. **Back up** `data/chroma/` (your library) and `data/sessions.db` (conversation history).
8. **Monitor Claude usage** — every `/chat` response reports `input_tokens` and `output_tokens`. Log them.

---

## Disclaimer

RegView is for **research and informational use only**. It is not medical, legal, or regulatory advice. Always verify important findings against the primary sources: [FDA.gov](https://www.fda.gov), [ClinicalTrials.gov](https://clinicaltrials.gov), and the official Orange Book.
