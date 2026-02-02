from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from typing import List, Dict, Any

from supabase_client import supabase
from dependencies import get_current_user

router = APIRouter(prefix="/profile", tags=["auth"])


def _date_bounds_for(date_str: str):
    # date_str expected YYYY-MM-DD
    start = datetime.fromisoformat(date_str)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return start.isoformat(), end.isoformat()


@router.get("/streak")
def getProfileStreak(user = Depends(get_current_user)):
    # keep existing RPC call
    response = supabase.rpc(
        "get_current_streak",
        {"p_profile_id": user["profile_id"]}
    ).execute()

    current_streak = response.data
    # Optionally include recent counts for last 7 days
    try:
        today = datetime.utcnow().date()
        start = (today - timedelta(days=6)).isoformat()
        end = today.isoformat()
        cal_resp = supabase.rpc(
            "get_user_calendar",
            {"p_profile_id": user["profile_id"], "p_start": start, "p_end": end}
        ).execute()
        recent_counts = cal_resp.data or []
    except Exception:
        recent_counts = []

    return {"current_streak": current_streak, "recent_counts": recent_counts}


@router.get("/calendar")
def get_profile_calendar(start: str = None, end: str = None, user = Depends(get_current_user)):
    # If start/end not provided, default to current month
    if not start or not end:
        today = datetime.utcnow()
        start = datetime(today.year, today.month, 1).date().isoformat()
        # last day of month
        next_month = datetime(today.year, today.month, 28) + timedelta(days=4)
        last = next_month - timedelta(days=next_month.day)
        end = last.date().isoformat()

    # Call RPC if available
    try:
        resp = supabase.rpc(
            "get_user_calendar",
            {"p_profile_id": user["profile_id"], "p_start": start, "p_end": end}
        ).execute()
        if resp.error:
            raise resp.error
        return resp.data
    except Exception:
        # Fallback: fetch rows and aggregate in Python
        start_ts = start + "T00:00:00Z"
        end_ts = end + "T23:59:59Z"
        q = supabase.table("user_solved_questions").select("id,question_id,solved_at").eq("user_id", user["profile_id"]).gte("solved_at", start_ts).lte("solved_at", end_ts).execute()
        rows = q.data or []
        counts: Dict[str, int] = {}
        for r in rows:
            d = r["solved_at"][0:10]
            counts[d] = counts.get(d, 0) + 1
        out = [{"date": k, "count": v} for k, v in counts.items()]
        out.sort(key=lambda x: x["date"])
        return out


@router.get("/solved/{date}")
def get_solved_on_date(date: str, user = Depends(get_current_user)):
    # date: YYYY-MM-DD
    try:
        start_ts, end_ts = _date_bounds_for(date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    resp = supabase.table("user_solved_questions").select("id,question_id,solved_at,metadata").eq("user_id", user["profile_id"]).gte("solved_at", start_ts).lte("solved_at", end_ts).order("solved_at", {"ascending": False}).execute()
    rows = resp.data or []

    # Fetch question metadata for listed question_ids if questions table exists
    qids = list({r["question_id"] for r in rows})
    questions_map: Dict[int, Dict[str, Any]] = {}
    if qids:
        try:
            qresp = supabase.table("questions").select("id,title,difficulty").in_("id", qids).execute()
            for q in qresp.data or []:
                questions_map[q["id"]] = q
        except Exception:
            questions_map = {}

    out = []
    for r in rows:
        item = {"id": r["id"], "question_id": r["question_id"], "solved_at": r["solved_at"], "metadata": r.get("metadata")}
        if r["question_id"] in questions_map:
            item["question"] = questions_map[r["question_id"]]
        out.append(item)

    return out
