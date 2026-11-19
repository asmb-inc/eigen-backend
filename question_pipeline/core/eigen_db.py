"""Access to Eigen's Supabase database.

Reading references uses the public key. Admin checks, creating admins and publishing
need SUPABASE_SERVICE_KEY, which bypasses row level security - keep it only on the server.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def has_service_key() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _request(method: str, path: str, key: str | None, **kwargs):
    if not SUPABASE_URL or not key:
        raise RuntimeError("Set SUPABASE_URL and the needed key in .env")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", **kwargs.pop("headers", {})}
    resp = requests.request(method, f"{SUPABASE_URL}{path}", headers=headers, timeout=30, **kwargs)
    if not resp.ok:
        raise RuntimeError(f"Supabase {method} {path} failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json() if resp.content else None


def _get(table: str, query: str) -> list[dict]:
    return _request("GET", f"/rest/v1/{table}?{query}", SUPABASE_KEY)


def fetch_questions() -> list[dict]:
    """Return every Eigen question with its answers attached, in the pipeline's reference format."""
    questions = _get("questions", "select=id,title,body,blanks_count,topics,difficulty&order=id")
    answers = _get("answers", "select=question_id,blank_order,value&order=question_id,blank_order")

    by_question = {}
    for a in answers:
        by_question.setdefault(a["question_id"], []).append(
            {"blank_order": a["blank_order"], "value": a["value"]}
        )

    return [{**q, "answers": by_question.get(q["id"], [])} for q in questions]


def is_admin(user_id: str) -> bool:
    rows = _request("GET", f"/rest/v1/admins?select=user_id&user_id=eq.{user_id}", SUPABASE_SERVICE_KEY)
    return bool(rows)


def create_admin(email: str, password: str) -> str:
    """Create a confirmed login for the admin and add them to the admins table. Returns the user id."""
    user = _request(
        "POST", "/auth/v1/admin/users", SUPABASE_SERVICE_KEY,
        json={"email": email, "password": password, "email_confirm": True},
    )
    _request("POST", "/rest/v1/admins", SUPABASE_SERVICE_KEY, json={"user_id": user["id"]})
    return user["id"]


def insert_question(q: dict) -> int:
    """Publish one approved question into Eigen's questions + answers tables. Returns the new question id."""
    rows = _request(
        "POST", "/rest/v1/questions", SUPABASE_SERVICE_KEY,
        headers={"Prefer": "return=representation"},
        json={
            "title": q["title"],
            "body": q["body"],
            "blanks_count": q["blanks_count"],
            "topics": q["topics"],
            "difficulty": q["difficulty"],
            "source": "ai",
        },
    )
    question_id = rows[0]["id"]
    try:
        _request("POST", "/rest/v1/answers", SUPABASE_SERVICE_KEY, json=[
            {"question_id": question_id, "blank_order": a["blank_order"], "value": a["value"]}
            for a in q["answers"]
        ])
    except RuntimeError:
        # never leave a question without answers - students could not solve it
        _request("DELETE", f"/rest/v1/questions?id=eq.{question_id}", SUPABASE_SERVICE_KEY)
        raise
    return question_id
