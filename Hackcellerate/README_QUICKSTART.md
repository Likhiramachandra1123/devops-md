# RegView — Super-Simple Local Test Guide (No API Key Needed)

This is the **"just get it working on my laptop"** guide.
Follow it top-to-bottom. Every command is copy-paste ready. No prior Python experience assumed.

You will **not** need an Anthropic (Claude) API key for anything in this guide.
The AI answer part is disabled — you'll only test the "search my documents" side.

---

## What you'll end up with

- A little program running on your own laptop at `http://localhost:8000`.
- A local "library" filled with real FDA drug + patent data.
- The ability to ask questions and see the top matching snippets from your library.
- **No costs. No internet calls to any paid service.**

---

## Step 1 — Install Python (one-time only)

1. Go to https://www.python.org/downloads/
2. Download **Python 3.11.x** (any 3.11 sub-version is fine).
3. Run the installer.
4. **VERY IMPORTANT:** On the first screen, tick the checkbox that says **"Add Python to PATH"**. If you miss this, nothing else in this guide will work.
5. Click **Install Now**. Wait for it to finish.

**Check it worked:**
- Press the `Windows` key.
- Type `PowerShell` and press Enter.
- In the black/blue window that opens, type this and press Enter:

  ```powershell
  python --version
  ```

- You should see something like `Python 3.11.9`. If you see an error, redo the install and make sure the "Add to PATH" box is ticked.

---

## Step 2 — Open the project folder

In that same PowerShell window, run:

```powershell
cd C:\Users\LikhithR\Documents\Hackcellerate
```

You are now "inside" the project folder. From here everything else works.

---

## Step 3 — Create a private sandbox for the project (one-time only)

This makes a private mini-Python inside the project so it doesn't mess with anything else on your PC.

```powershell
python -m venv .venv
```

Wait ~10 seconds. A new folder called `.venv` appears. **Done — you never do this step again.**

---

## Step 4 — Turn ON the sandbox (every time you open a new PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
```

**How you know it worked:** the prompt now starts with `(.venv)` like this:

```
(.venv) PS C:\Users\LikhithR\Documents\Hackcellerate>
```

### If you get a red error saying "running scripts is disabled"

Run this ONE line (only once, ever):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Say `Y` when it asks. Then re-run the activate command above.

### If clicking Activate.ps1 just opens Notepad

You are in **Command Prompt (cmd)**, not PowerShell. Close it. Reopen the correct one: `Windows key` → type `PowerShell` → Enter.

---

## Step 5 — Install everything the project needs (one-time only)

Still inside the `(.venv)` prompt, run:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**This takes 5 to 10 minutes.** Lots of scrolling text is normal.

When it finishes with no red errors, you're done with this step forever.

### If you see "To modify pip, please run … python.exe -m pip install --upgrade pip"

Ignore it. It's a Windows quirk. Just run the next line (`pip install -r requirements.txt`) and continue.

---

## Step 6 — Create your settings file (one-time only)

```powershell
copy .env.example .env
```

That's it. **You do NOT need to add an Anthropic key for this guide.** The program will boot fine without one — the AI-answer part will just be disabled.

---

## Step 7 — Start the server

```powershell
uvicorn app.main:app --reload --port 8000
```

The first time you run this, it will download a search-AI model called PubMedBERT (~440 MB). **This takes 1–2 minutes.** Progress bars are normal.

You'll know it's ready when you see something like:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

🎉 **Your program is now running.**

> ⚠️ **Leave this window open and running.** Do not close it. Do not press Ctrl+C. Any messages that scroll by are normal logs.

---

## Step 8 — Test it's alive (in a new window)

Now you need a **second** PowerShell window, because the first one is busy running the server.

1. Press `Windows` key → type `PowerShell` → Enter. A new PowerShell window opens.
2. In the new window run:

   ```powershell
   cd C:\Users\LikhithR\Documents\Hackcellerate
   .\.venv\Scripts\Activate.ps1
   ```

3. Now check the server is alive:

   ```powershell
   curl http://localhost:8000/health
   ```

   You should see a JSON blob with `"status":"ok"` in it. If you do, everything is working.

Or open your web browser and visit **http://localhost:8000/docs** — you'll see a colorful page with all the API endpoints laid out. This is the easiest way to click around.

---

## Step 9 — Fill the library with real FDA data

Right now the library is empty. Let's put real FDA data into it so we have something to search.

In the **second** PowerShell window (from Step 8), run:

```powershell
python -m scripts.ingest_bulk --only labels --labels-max 500
```

**What this does:** downloads 500 FDA drug labels (approved uses, dosing, warnings, side effects) directly from the openFDA API (`api.fda.gov`) and adds them to your local library.

**Expect this to take 3–8 minutes.** You'll see progress lines like:

```
openFDA drug/label: bulk fetch up to 500 records ...
  ... 200 labels ingested so far (450 chunks)
  ... 400 labels ingested so far (900 chunks)
=== openFDA drug labels done in 240.3s — 500 docs / 1150 chunks ===
BULK INGEST COMPLETE — 500 docs, 1150 chunks, 1150 total chunks in ChromaDB
```

That's it — you now have real FDA drug label data locally.

### Want more data too?

Skip this if you're just testing. If you want the full experience, run these later (each one takes a while):

```powershell
# All 25,000 drug labels (openFDA API cap) — takes ~30 min
python -m scripts.ingest_bulk --only labels

# 1,000 clinical trials
python -m scripts.ingest_bulk --only clinicaltrials --trials-limit 1000

# 5,000 FDA drug recall/enforcement records
python -m scripts.ingest_bulk --only drug_enforce --enforce-max 5000

# EVERYTHING with sensible defaults (~1–2 hours, 2–5 GB disk)
python -m scripts.ingest_bulk
```

### About the Orange Book

The `--only orangebook` step downloads a ZIP file from `www.fda.gov` (not the API host). Some corporate networks and VPNs block that server, causing an empty/silent failure. If you get `Orange Book failed:` with no useful message, that's what's happening. The other steps (`labels`, `510k`, `drug_enforce`, `device_enforce`, `food_enforce`, `clinicaltrials`) all use different hosts and should work fine — use those instead.

---

## Step 10 — Ask it a question

Still in the **second** PowerShell window:

```powershell
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{\"message\":\"What is atorvastatin approved for?\"}'
```

Because you don't have an Anthropic key, the answer won't be a polished AI paragraph — instead you'll get back **the top matching snippets from your local library** along with a note saying "Claude is disabled". This proves your search is working.

The response includes:

- `session_id` — a unique ID for this conversation. Save it if you want to ask follow-ups.
- `answer` — the raw matching snippets from FDA data.
- `citations` — where each snippet came from, with URLs.
- `grounded: true` — means it found relevant stuff in your library.
- `model: "none (no ANTHROPIC_API_KEY)"` — a reminder that AI writing is off.

### Prefer clicking to typing?

1. Go to **http://localhost:8000/docs** in your browser.
2. Find the box labeled **POST /chat**.
3. Click **Try it out**.
4. In the JSON box, type your question:

   ```json
   {"message": "What is atorvastatin approved for?"}
   ```

5. Click **Execute**. Scroll down for the answer.

---

## Step 11 — Try more questions

Some good ones to test with (all should return real FDA snippets):

- "Show me approved uses of metformin"
- "What are the patents for ibuprofen?"
- "Tell me about paracetamol"
- "When does Lipitor's patent expire?"
- "What drugs contain amoxicillin?"

If you added the extra data in Step 9, also try:

- "What clinical trials exist for diabetes?"
- "Any recalls involving contamination?"

---

## Step 12 — Stopping and restarting

**To stop the server:** go back to the **first** PowerShell window and press `Ctrl+C`. Wait a second for it to shut down.

**To start it again later:** open PowerShell, then:

```powershell
cd C:\Users\LikhithR\Documents\Hackcellerate
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

You do **NOT** need to re-run steps 3, 5, 6, or 9 — those are one-time. Your library is saved in `data\chroma\` on your disk and persists between restarts.

---

## What can go wrong (and how to fix it)

### "python is not recognized"

You skipped the "Add Python to PATH" checkbox during install. **Reinstall Python** and tick the box this time.

### The server window shows red text and exits

Read the last line of red text. Usually it means:
- **Port 8000 already in use** → change to a free port: `uvicorn app.main:app --reload --port 8080` (then use 8080 in all URLs above).
- **Module not found** → you forgot Step 4 (`Activate.ps1`). The prompt must start with `(.venv)`.

### "Activate.ps1 just opened Notepad"

You're in Command Prompt (cmd) instead of PowerShell. Close it. Open **PowerShell** properly: `Windows key` → type `PowerShell` → Enter.

### Every question comes back with "grounded: false"

Your library is empty. Redo **Step 9**. Then check:

```powershell
curl http://localhost:8000/ingest/stats
```

You should see a number like `{"chunk_count": 5432}`. If it's `0`, ingest failed — scroll up in the ingest window for the error.

### The first `/chat` call takes ~30–60 seconds

Normal. The AI model has to load into memory the first time. Later questions are fast (~1 second).

### `ingest_bulk --only orangebook` fails with no error message

The Orange Book is served from `www.fda.gov`, which is blocked on many corporate networks and some VPNs (returns 404 for everything). The openFDA **API** (`api.fda.gov`) is a separate host and usually works fine. Use these steps instead:

```powershell
python -m scripts.ingest_bulk --only labels --labels-max 500
python -m scripts.ingest_bulk --only 510k --510k-max 500
python -m scripts.ingest_bulk --only drug_enforce --enforce-max 500
python -m scripts.ingest_bulk --only clinicaltrials --trials-limit 500
```

If you want the Orange Book specifically, try from a home/personal-hotspot network, or download the ZIP manually from https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files, unzip into `data\documents\orangebook\`, and run `python -m scripts.ingest_documents --path .\data\documents\orangebook`.

---

## What you have now

- ✅ A real production-quality backend running on your laptop.
- ✅ A local searchable library of FDA regulatory data.
- ✅ Working retrieval (search) — you can verify quality without paying anything.
- ❌ AI-written answers — this needs an Anthropic API key. When you're ready, get one from https://console.anthropic.com/ and paste it into `.env` on the `ANTHROPIC_API_KEY=` line. No code changes needed — Claude will start answering automatically.

---

## Where things live on your disk

- `data\chroma\` — your searchable library (grows as you ingest more).
- `data\sessions.db` — your saved conversations.
- `data\documents\` — put your own PDFs / Word files here, then run `python -m scripts.ingest_documents --path .\data\documents` to add them.
- `.env` — your settings (add your Claude key here later).

You can delete `data\chroma\` any time to reset the library. You can safely back up the whole `data\` folder.

---

## When you're ready to unlock full AI answers

1. Get an Anthropic API key: https://console.anthropic.com/ → API Keys → Create Key. (Costs money per question, usually pennies each.)
2. Open `.env` in Notepad.
3. Replace `ANTHROPIC_API_KEY=` with `ANTHROPIC_API_KEY=sk-ant-...your-key...`.
4. Save.
5. Stop the server (`Ctrl+C`) and restart it (`uvicorn app.main:app --reload --port 8000`).
6. Ask a question again — you'll now get a polished 3-4 line AI answer with citations, instead of raw snippets.

That's it. Same commands, same URLs, same everything — just now with the AI writing the answers.
