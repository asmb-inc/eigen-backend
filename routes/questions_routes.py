from fastapi import APIRouter, Depends, HTTPException
from schemas import GetOTPRequest
from supabase_client import supabase 
from dependencies import get_current_user
from datetime import datetime, timezone, timedelta
from schemas import PostAnswerRequest, GetQuestionByDateString
from math import isclose
from datetime import datetime, timezone
import calendar
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



@router.get('/daily/{date}')
def getDailyQuestionByDate(date: str, user=Depends(get_current_user)):
    # date expected YYYY-MM-DD
    try:
        # build bounds
        start = date + 'T00:00:00Z'
        end = date + 'T23:59:59Z'
        response = supabase.table('daily_questions').select('*').gte('created_at', start).lte('created_at', end).order('created_at', desc=True).limit(1).execute()
        if response.data and len(response.data) > 0:
            daily_q = response.data[0]
            question_id = daily_q.get('question_id')
            questions = supabase.table('questions').select('*').eq('id', question_id).execute()
            if questions.data:
                return questions.data[0]
        raise HTTPException(status_code=404, detail="No daily question found for that date")
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
    # print(answers)
    # print(id)
    resp = (
        supabase
        .table("answers")
        .select("id","blank_order, value")
        .eq("question_id", id)
        .order("blank_order")
        .execute()
    )

    correct_answers = resp.data
    print("REACHING HERE 1")
    if len(answers) != len(correct_answers):
        print("CONDITION HITTING")
        raise HTTPException(
            status_code=400,
            detail="Number of answers does not match number of blanks",
        )

    results = []
    all_correct = True
    print("REACHING HERE 2")

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
            "answer_id": correct['id']
        })

        if not is_correct:
            all_correct = False 
    print("REACHING HERE 3")

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
           except Exception as e:
                print(f"Error submitting answer: {e}")
                raise HTTPException(status_code = 400, detail = "Sorry we have trouble submitting the answer in the moment")
    
    
    print("PRINTING THE RESULTS")
    submissions = []
    for result in results: 
       if(result['submitted'] != None):
            submissions.append({'question_id': id, 'answer_id': result['answer_id'], 'profile_id': user['profile_id'], 'is_correct': result['is_correct'], 'answer_value': result['submitted']})
    
    try:
        resp = (
        supabase.table('submissions')
                .upsert(submissions, on_conflict='profile_id,question_id,answer_id')
                .execute()
        )
    except Exception as e:
        print(f"Error submitting answer: {e}")
        raise HTTPException(status_code = 400, detail = "Sorry we have trouble submitting the answer in the moment")
    print(resp.data)
    print("we are progressing till here")
    # NOW WE ARE STORING JUST EXTENDING THIS SUBMISSIONS API NEELESSLY, THE CORRECT APPROACH IS USING ASYNC WORKER WITH KAFKA  
    try:
       
                
        res = supabase.rpc(
        "upsert_submission_status",
        {
            "q_id": id,
            "p_id": user['profile_id']
        }
        ).execute()
        
        print
        
    except Exception as e:
        print(f"Error submitting answer: {e}")
        raise HTTPException(status_code = 400, detail = "error in updating submission_answers table")
    
    
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




# used in the below route
def get_month_range(year_month: str):
    year, month = map(int, year_month.split("-"))
    start = datetime(year, month, 1, 0, 0, 0)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59)
    return start, end
 
 
#  2026-02
@router.get('/month-status/{month}')
def getMonthStatus(month: str,user = Depends(get_current_user)):
    # need to fetch question_ids
    start, end  = get_month_range(month)
    try:
         
        resp = (
            supabase 
            .table('daily_questions')
            .select('question_id', 'created_at')
            .gte('created_at', start)
            .lte('created_at', end)
            .execute()
        )
        
        questions = resp.data
        question_ids = []
        for question in questions:
            question_ids.append(question['question_id'])
        
        
        

        print("THIS IS SUBMISSIONS")
        print(resp.data)
        
        # Query submissions_answers table
        submissions_resp = (
            supabase
            .table('submissions_answers')
            .select('*')
            .in_('question_id', question_ids)
            .eq('profile_id', user['profile_id'])
            .execute()
        )
        
        # Create dict for question_id to created_at
        question_created_at = {q['question_id']: q['created_at'] for q in questions}
        print(submissions_resp.data)
        # Filter rows where updated_at is on the same day as the question's created_at (basically we are saying if question not solved AT the same day 
        # it was created a as a daily question for the calender mark it as UNSOLVED)
        filtered_submissions = [
            submission for submission in submissions_resp.data
            if submission['updated_at'][:10] == question_created_at.get(submission['question_id'])[:10]
        ]
        print("THIS IS FILTERED SUBMISSIONS")
        print(filtered_submissions)
        
        # Get year and month
        year, month_num = map(int, month.split("-"))
        last_day = calendar.monthrange(year, month_num)[1]
        
        # Initialize all days as unsolved
        month_status = {f"{day:02d}": "unsolved" for day in range(1, last_day + 1)}
        
        # Update status for days with submissions
        for submission in filtered_submissions:
            day = submission['updated_at'][:10].split('-')[2]  # Extract DD from YYYY-MM-DD
            month_status[day] = submission['status']
        
        # Return list of day-status pairs
        response = [{"day": day, "status": status} for day, status in month_status.items()]
        print(response)
        return response
    except Exception as e:
        print(e)
        raise HTTPException(status_code = 400, detail = "cannot load calendar ")
    