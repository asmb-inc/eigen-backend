# Running the backend

**Quick Local (Windows PowerShell)**

- Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- Start the app:

```powershell
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- Optional: use the included helper script:

```powershell
.\run_local.ps1
```

**Using Docker Compose**

- Build and run with Docker Compose (requires Docker):

```bash
docker build -t battlon-backend:latest .
docker-compose up --build
# Stop and remove containers
docker-compose down
```

Notes:
- If your code expects environment variables, create a `.env` file in the repo root (copy from `.env.example` if present).
- API runs on port 8000 by default.

# AI question generation pipeline

Generates new Eigen-style questions (LaTeX body, numeric fill-in-the-blank answers) with an LLM,
based on the questions already in Eigen. Nothing reaches students without a person approving it.

```
existing Eigen question (reference)
  -> LLM writes new questions: same concept, new setting/wording/numbers
  -> validator: format, blanks = answers, numeric answers, difficulty
  -> verifier: the LLM solves each question again without seeing the answer
  -> draft  ->  admin reviews / edits / sets difficulty  ->  approved | rejected
  -> publish  ->  Eigen questions + answers tables (source = 'ai')
```

- Code: `question_pipeline/core/` (no printing / input, reused by the CLI and the API)
- Terminal interface: `question_pipeline/cli.py`
- Admin API for the app: `routes/admin_questions_routes.py`
- Tests: `tests/`

## 1. Setup

Use **Python 3.10 - 3.12** (some packages in `requirements.txt` do not install on 3.14 yet).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`:

| Setting | What |
|---|---|
| `SUPABASE_URL`, `SUPABASE_KEY` | Eigen's Supabase URL and public (anon) key, used to read existing questions |
| `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Which LLM to use. `openai` = any OpenAI-compatible API (Groq, DeepSeek, Together, OpenAI); `ollama` = local Ollama or Ollama cloud. Switching provider only changes these lines. |
| `LLM_MAX_TOKENS`, `LLM_REASONING_EFFORT` | For "thinking" models like gpt-oss: room for the answer and less reasoning (6000 / low) |
| `ADMIN_EMAILS` | Temporary admin list for the API until the `admins` table exists (comma separated) |
| `SUPABASE_SERVICE_KEY` | Server only. Needed for the `admins` table, `create-admin` and publishing into Supabase. Without it, publish writes only to a local file. |

## 2. Test

```powershell
python -m unittest discover tests
```

Uses a fake LLM and a fake Supabase: no keys, no internet, no real data touched.
Expect `Ran 28 tests ... OK`.

## 3. Generate

```powershell
python -m question_pipeline.cli fetch-references                   # read existing Eigen questions (read-only)
python -m question_pipeline.cli topics                             # topics that have reference questions
python -m question_pipeline.cli generate --topic optics --count 2  # based on Eigen's optics questions
python -m question_pipeline.cli generate --topic probability --count 2 --difficulty 800   # new topic, no reference
python -m question_pipeline.cli generate --all --count 1           # one per existing question
```

New questions are saved as **drafts** in `question_pipeline/data/questions.json` (not committed).

## 4. Open and review

```powershell
python -m question_pipeline.cli list --status draft
python -m question_pipeline.cli review       # a = approve, r = reject (with reason), e = edit JSON, s = skip, q = quit
python -m question_pipeline.cli export       # HTML page with the maths rendered, to read or share
start question_pipeline\data\report.html
```

For each question check that the blank is in the right place and the answer is right.
`verifier: MISMATCH` means the LLM got a different answer when re-solving it: check it by hand.
It catches real mistakes, but the verifier is an LLM too and is sometimes the one that is wrong.

## 5. Publish

```powershell
python -m question_pipeline.cli publish
```

Sends every approved question to Eigen's `questions` and `answers` tables (`source = 'ai'`) when
`SUPABASE_SERVICE_KEY` is set; otherwise only to `question_pipeline/data/published.json`.
If a question cannot be saved, it stays approved so it can be retried; a question is never left without answers.

## 6. Admin API (for the app)

Start the server and open http://localhost:8000/docs:

```powershell
python -m uvicorn app:app --port 8000
```

| Route | Purpose |
|---|---|
| `GET /admin/questions/check` | 200 if the logged-in user is an admin |
| `GET /admin/questions/topics` | Topics for the generate screen |
| `POST /admin/questions/generate` | `{"topic": "optics", "count": 3}` or `{"all_references": true, "count": 1}`. Returns a job id at once |
| `GET /admin/questions/jobs/{id}` | Job status: running / done / failed |
| `GET /admin/questions?status=draft` | List questions by status |
| `GET /admin/questions/{id}` | One question |
| `PATCH /admin/questions/{id}` | Edit text, answers, difficulty, topics (validated) |
| `POST /admin/questions/{id}/approve` | Approve |
| `POST /admin/questions/{id}/reject` | Reject, `{"note": "reason"}` |
| `POST /admin/questions/publish` | Publish all approved |

All routes need a logged-in Supabase user (Bearer token) who is an admin.

## 7. One-time setup in Supabase (needs dashboard access)

1. Run `question_pipeline/sql/001_admins.sql` in the SQL editor (creates the `admins` table).
2. Set `SUPABASE_SERVICE_KEY` on the server (Supabase -> Settings -> API -> `service_role`). Never put it in the app.
3. Create an admin login: `python -m question_pipeline.cli create-admin --email someone@example.com` (password is asked hidden).

## Known limits

- Drafts are stored in a local JSON file. On Vercel the file system is temporary, so before deploying the
  admin API, drafts should move to a Supabase table.
- Generation quality depends on the model: the validator and verifier catch many mistakes, but every question still needs a human review.
