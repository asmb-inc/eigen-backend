import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
QUESTIONS_FILE = DATA_DIR / "questions.json"
PUBLISHED_FILE = DATA_DIR / "published.json"

# draft -> approved -> published, or draft -> rejected
STATUSES = ("draft", "approved", "rejected", "published")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_all() -> list[dict]:
    if not QUESTIONS_FILE.exists():
        return []
    return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))


def _save_all(questions: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUESTIONS_FILE.write_text(json.dumps(questions, indent=2, ensure_ascii=False), encoding="utf-8")


def list_questions(status: str | None = None) -> list[dict]:
    questions = load_all()
    if status:
        questions = [q for q in questions if q["status"] == status]
    return questions


def get_question(question_id: str) -> dict | None:
    return next((q for q in load_all() if q["id"] == question_id), None)


def add_drafts(new_questions: list[dict], reference: str | None = None) -> list[dict]:
    """Save generated questions with status 'draft'. Returns the saved records."""
    questions = load_all()
    saved = []
    for q in new_questions:
        record = {
            "id": uuid.uuid4().hex[:8],
            "status": "draft",
            **q,
            "source": "ai",  # matches the questions.source column in Eigen ('human' for hand-written ones)
            "reference": reference,
            "created_at": _now(),
            "reviewed_at": None,
            "review_note": None,
        }
        questions.append(record)
        saved.append(record)
    _save_all(questions)
    return saved


def update_question(question_id: str, changes: dict) -> dict:
    questions = load_all()
    for q in questions:
        if q["id"] == question_id:
            q.update(changes)
            _save_all(questions)
            return q
    raise KeyError(f"No question with id {question_id}")


def set_status(question_id: str, status: str, note: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    return update_question(question_id, {"status": status, "reviewed_at": _now(), "review_note": note})


def publish_approved(push=None) -> dict:
    """Publish every approved question and write all published ones to published.json.

    `push(question) -> eigen_id` sends a question to Eigen's database. If it fails, that question
    stays 'approved' so it can be retried. Without `push`, questions are only published locally.
    """
    questions = load_all()
    newly_published, failed = [], []
    for q in questions:
        if q["status"] != "approved":
            continue
        if push:
            try:
                q["eigen_question_id"] = push(q)
            except Exception as e:
                failed.append({"id": q["id"], "error": str(e)})
                continue
        q["status"] = "published"
        q["published_at"] = _now()
        newly_published.append(q)
    _save_all(questions)

    published = [q for q in questions if q["status"] == "published"]
    PUBLISHED_FILE.write_text(json.dumps(published, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"published": newly_published, "failed": failed}
