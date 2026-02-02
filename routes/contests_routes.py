from fastapi import APIRouter, Depends, HTTPException, status
from supabase_client import supabase
from dependencies import get_current_user
from datetime import datetime, timezone

router = APIRouter(prefix='/contests', tags=['contests'])


@router.get('/{contest_id}')
def get_contest(contest_id: str):
    """Return contest details including question IDs."""
    resp = (
        supabase
        .table('contests')
        .select('*')
        .eq('id', contest_id)
        .limit(1)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Contest not found')

    contest = resp.data[0]

    # Fetch question IDs for this contest
    qresp = (
        supabase
        .table('questions')
        .select('id')
        .eq('contestId', contest_id)
        .execute()
    )

    question_ids = [q['id'] for q in (qresp.data or [])]

    return {
        'id': contest.get('id'),
        'name': contest.get('name'),
        'startTime': contest.get('startTime'),
        'questions': question_ids,
    }


@router.get('/{contest_id}/questions')
def get_contest_questions(contest_id: str, user = Depends(get_current_user)):
    """Return full question objects for a contest.

    Requires authentication. Access is denied if the contest hasn't started yet.
    """
    cresp = (
        supabase
        .table('contests')
        .select('*')
        .eq('id', contest_id)
        .limit(1)
        .execute()
    )

    if not cresp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Contest not found')

    contest = cresp.data[0]

    start_time_raw = contest.get('startTime')
    if start_time_raw:
        try:
            # Expect ISO formatted string; fallback if already datetime
            if isinstance(start_time_raw, str):
                start_time = datetime.fromisoformat(start_time_raw)
            else:
                start_time = start_time_raw

            # Ensure timezone-aware comparison (assume UTC if naive)
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)

        except Exception:
            # If parsing fails, deny access for safety
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid contest startTime')

        now = datetime.now(timezone.utc)
        if now < start_time:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Contest has not started yet')

    # Fetch full questions
    qresp = (
        supabase
        .table('questions')
        .select('*')
        .eq('contestId', contest_id)
        .execute()
    )

    return qresp.data or []


