from fastapi import APIRouter, Depends, HTTPException
from schemas import GetOTPRequest
from supabase_client import supabase 
from dependencies import get_current_user
from datetime import datetime, timezone, timedelta
from schemas import PostAnswerRequest, GetQuestionByDateString
from math import isclose
from datetime import datetime, timezone
router = APIRouter(prefix = '/questions', tags = ['auth'])
 

@router.get('/daily')
def getDailyQuestion(user=Depends(get_current_user)):
    try:
        response = supabase.table('daily_questions').select('*').order('created_at', desc=True).limit(1).execute()    
        if response.data:
            daily_q = response.data[0]
            question_id = daily_q.get('question_id')
            questions = supabase.table('questions').select('*').eq('id', question_id).execute()
            if questions.data:
                return questions.data[0]
        else:
            raise HTTPException(status_code=404, detail="No daily question found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@router.get('/all')
def getAllQuestions(user=Depends(get_current_user)):
    questions = supabase.table('questions').select('*').execute()
    return questions.data


@router.get('/{id}')
def getQuestionById(id: int, user = Depends(get_current_user)):
    question = supabase.table('questions').select('*').eq('id', id).limit(1).execute()
    if not question.data:
        raise HTTPException(status_code = 404, detail = "No question found")    
    return question.data[0]






@router.post('/{id}/answer')
def postAnswerOfTheQuestion(
    id: int,
    request: PostAnswerRequest,
    user=Depends(get_current_user),
):
    answers = request.answers
    print(answers)
    print(id)
    resp = (
        supabase
        .table("answers")
        .select("blank_order, value")
        .eq("question_id", id)
        .order("blank_order")
        .execute()
    )

    correct_answers = resp.data
    print(correct_answers)
    if len(answers) != len(correct_answers):
        raise HTTPException(
            status_code=400,
            detail="Number of answers does not match number of blanks",
        )

    results = []
    all_correct = True

    for user_answer, correct in zip(answers, correct_answers):
        correct_value = float(correct["value"])

       
        if user_answer is None:
            is_correct = False
        else:
            is_correct = isclose(
                user_answer,
                correct_value,
                rel_tol=1e-3,
                abs_tol=1e-3,
            )

        results.append({
            "blank_order": correct["blank_order"],
            "submitted": user_answer,
            "is_correct": is_correct,
        })

        if not is_correct:
            all_correct = False

    # check if all correct then is it a daily question if so then update the streak
    if (all_correct):
        print("WE ARE HITTING ALL CORRECT")
        resp = supabase.table('daily_questions').select('*').order('created_at', desc = True).limit(1).execute()
        dailyquestion = resp.data[0]
        # if only the question solved by the user is a daily question
        if (dailyquestion['question_id'] == id):
           print("WE ARE ALSO HITTING DAILY QUESTION")
           today = datetime.now(timezone.utc).date().isoformat()
           try:
               supabase.table('streak').insert({'profile_id': user['profile_id'], 'created_at_date': today}).execute()
           except:
               pass
    
    return {
        "question_id": id,
        "all_correct": all_correct,
        "results": results,
    }






@router.post('/get-daily-question-by-datestring')
def getDailyQuestionByDateString(request: GetQuestionByDateString, user=Depends(get_current_user)):
    print("question is reaching here")
 
    date_str = request.datestring
    # build a timestamp range covering that day in UTC
    start_ts = f"{date_str}T00:00:00Z"
    end_ts = f"{date_str}T23:59:59Z"

    resp = (
        supabase
        .table('daily_questions')
        .select('question_id')
        .gte('created_at', start_ts)
        .lte('created_at', end_ts)
        .limit(1)
        .execute()
    )

    if resp.data and len(resp.data) > 0:
        return {"question_id": resp.data[0].get('question_id')}
    else:
        raise HTTPException(status_code=404, detail="No entry for that date")
 