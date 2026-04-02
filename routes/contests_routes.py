from fastapi import APIRouter, Depends, HTTPException, status
from supabase_client import supabase
from dependencies import get_current_user
from datetime import datetime, timezone
from schemas import SubmitContestRequest
from collections import defaultdict
from math import isclose
from datetime import datetime, timezone


router = APIRouter(prefix='/contests', tags=['contests'])



@router.get('')
def getContests(user = Depends(get_current_user)):
    try:
        resp = supabase.table('contests').select('*').execute()
        contests = resp.data
        print(contests)
        return contests
    except Exception as e:
        print(e)
        raise HTTPException(status_code = 400, detail = "Sorry cannot get questions")

@router.get('/{id}')
def getContest(id: int, user = Depends(get_current_user)):
    try:
        resp = supabase.table('contests').select('*').eq('id', id).execute()
        contest = resp.data[0] if resp.data else None
        if not contest:
            raise HTTPException(status_code=404, detail="Contest not found")
        return contest
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Sorry cannot get contest")
    
# creats a submission row (will safeguard against double begins. if statement for behin in UI )
# increments total participants
@router.get('/{id}/begin')
def beginContest(id: int, user = Depends(get_current_user)):
    try:
        resp = (supabase.table('contest_submissions')
        .insert({'profile_id': user['profile_id'], 'contest_id': id}).execute())
        print(resp.data)
        resp = supabase.rpc("increment_column", {"row_id": id}).execute()
        return "ok"
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Sorry cannot begin contest")
    
@router.get('/{id}/questions')
def beginContest(id: int, user = Depends(get_current_user)):
    try:
        resp = (supabase.table('questions').select('*').eq('contest_id', id).execute())
        questions = resp.data
        return questions
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Sorry cannot questions of  contest")
    

@router.get('/{id}/can-enter')
def canEnterContest(id: int, user=Depends(get_current_user)):
    try:
        resp = (
            supabase
            .table("contest_submissions")
            .select("did_submit")
            .eq("contest_id", id)
            .eq("profile_id", user["profile_id"])
            .maybe_single()
            .execute()
        )

        data = resp.data

        # ❌ No entry found → user hasn't entered
        if data is None:
            return {"status": "not_entered"}

        # ✅ Entry exists
        if data["did_submit"]:
            return {"status": "is_submitted"}
        else:
            return {"status": "ongoing"}

    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=400,
            detail="Sorry cannot fetch contest status"
        )
        

@router.post('/{id}')
def submitContest(id: int, submission: SubmitContestRequest, user=Depends(get_current_user)):
    submitted_answers = submission.answers
    total_score = 0

    print("Submitted:", submitted_answers)

    # ⚠️ Ensure keys are ints (very important if coming from JSON)
    submitted_answers = {int(k): v for k, v in submitted_answers.items()}
    question_ids = list(submitted_answers.keys())

    if not question_ids:
        return {"score": 0}

    # ✅ Fetch correct answers
    correct_resp = (
        supabase
        .table("answers")
        .select("question_id, blank_order, value")
        .in_("question_id", question_ids)
        .execute()
    )

    if correct_resp.data is None:
        raise HTTPException(500, "Error fetching answers")

    # ✅ Group correct answers: {qid: {blank_order: value}}
    correct_map = defaultdict(dict)
    for row in correct_resp.data:
        qid = int(row["question_id"])
        order = int(row["blank_order"])
        correct_map[qid][order] = row["value"]

    # ✅ Fetch question difficulty
    question_resp = (
        supabase
        .table("questions")
        .select("id, difficulty")
        .in_("id", question_ids)
        .execute()
    )

    if question_resp.data is None:
        raise HTTPException(500, "Error fetching questions")

    difficulty_map = {
        int(q["id"]): q["difficulty"] for q in question_resp.data
    }

    # ✅ Evaluate answers
    for qid, user_answers in submitted_answers.items():
        correct_answers = correct_map.get(qid, {})

        # ⚠️ If no correct answers found → skip
        if not correct_answers:
            continue

        is_correct = True

        print(f"\nQID: {qid}")
        print("User:", user_answers)
        print("Correct:", correct_answers)

        for idx, correct_value in correct_answers.items():
            # ✅ FIX: convert 1-based index → 0-based
            user_val = user_answers[idx - 1] if (idx - 1) < len(user_answers) else None

            print(f"Comparing idx {idx}: user={user_val}, correct={correct_value}")

            # ✅ FIX: handle type mismatch
            if (not isclose(
                user_val,
                correct_value,
                rel_tol=1e-3,
                abs_tol=1e-3,
            )):
                is_correct = False
                break

        if is_correct:
            score_to_add = difficulty_map.get(qid, 0) or 0
            print(f"✅ Correct! Adding {score_to_add}")
            total_score += score_to_add
        else:
            print("❌ Incorrect")

    print("\nFinal Score:", total_score)
    try:
        resp = supabase.table("contest_submissions") \
                    .select("created_at") \
                    .eq("profile_id", user['profile_id']) \
                    .eq("contest_id", id) \
                    .single() \
                    .execute()

        created_at = datetime.fromisoformat(resp.data["created_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        duration = (now - created_at).total_seconds()

        # update
        supabase.table("contest_submissions") \
            .update({
                "score": total_score,
                "did_submit": True,
                "time": duration
            }) \
            .eq("profile_id", user['profile_id']) \
            .eq("contest_id", id) \
            .execute()
    except Exception as e:
        print(e)
        raise HTTPException(500, "Error fetching questions")
    
    
    
    return {
        "score": total_score
    }