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
