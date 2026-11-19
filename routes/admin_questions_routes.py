import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from dependencies import get_current_user
from question_pipeline.core import eigen_db, pipeline, references, store
from question_pipeline.core.validator import validate_question
from schemas import GenerateQuestionsRequest, RejectQuestionRequest, UpdateGeneratedQuestionRequest

router = APIRouter(prefix='/admin/questions', tags=['admin'])


# With SUPABASE_SERVICE_KEY set, admins come from the `admins` table (question_pipeline/sql/001_admins.sql).
# Without it (before the table exists), only emails listed in ADMIN_EMAILS in .env are admins.
def get_current_admin(user=Depends(get_current_user)):
    if eigen_db.has_service_key():
        try:
            allowed = eigen_db.is_admin(user["id"])
        except RuntimeError as e:
            print(e)
            raise HTTPException(status_code=503, detail="Could not check admin access")
    else:
        admins = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
        allowed = (user.get("email") or "").lower() in admins

    if not allowed:
        raise HTTPException(status_code=403, detail="Admins only")
    return user


# Generation takes minutes, so it runs in the background and the app polls the job.
# Kept in memory: jobs are lost if the server restarts (the drafts they saved are not).
jobs = {}


def _run_generation(job_id: str, request: GenerateQuestionsRequest):
    try:
        if request.all_references:
            saved, invalid = [], []
            for ref in references.load_references():
                result = pipeline.run(ref, request.count, reference_name=ref["_file"])
                saved += result["saved"]
                invalid += result["invalid"]
        else:
            result = pipeline.run_for_topic(request.topic, request.count, request.difficulty)
            saved, invalid = result["saved"], result["invalid"]

        jobs[job_id].update({
            "status": "done",
            "saved_ids": [q["id"] for q in saved],
            "dropped": len(invalid),
        })
    except Exception as e:  # any failure should mark the job failed, not leave it "running"
        print(e)
        jobs[job_id].update({"status": "failed", "error": str(e)})


# The app calls this after login: 200 means show the admin screens, 403 means a normal user
@router.get('/check')
def checkAdmin(admin=Depends(get_current_admin)):
    return {"admin": True}


@router.get('/topics')
def getTopics(admin=Depends(get_current_admin)):
    topics = references.list_topics()
    return [{"topic": name, "reference_count": n} for name, n in topics.items()]


@router.post('/generate', status_code=202)
def generateQuestions(request: GenerateQuestionsRequest, background_tasks: BackgroundTasks, admin=Depends(get_current_admin)):
    if not request.all_references and not (request.topic and request.topic.strip()):
        raise HTTPException(status_code=400, detail="Give a topic or set all_references")
    if not 1 <= request.count <= 10:
        raise HTTPException(status_code=400, detail="count must be between 1 and 10")

    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"id": job_id, "status": "running", "request": request.model_dump()}
    background_tasks.add_task(_run_generation, job_id, request)
    return jobs[job_id]


@router.get('/jobs/{job_id}')
def getJob(job_id: str, admin=Depends(get_current_admin)):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@router.get('')
def getGeneratedQuestions(status: str | None = None, admin=Depends(get_current_admin)):
    if status and status not in store.STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {store.STATUSES}")
    return store.list_questions(status)


@router.get('/{question_id}')
def getGeneratedQuestion(question_id: str, admin=Depends(get_current_admin)):
    question = store.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.patch('/{question_id}')
def updateGeneratedQuestion(question_id: str, request: UpdateGeneratedQuestionRequest, admin=Depends(get_current_admin)):
    question = store.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    if question["status"] == "published":
        raise HTTPException(status_code=400, detail="Published questions cannot be edited")

    changes = request.model_dump(exclude_none=True)
    errors = validate_question({**question, **changes})
    if errors:
        raise HTTPException(status_code=400, detail=errors)
    return store.update_question(question_id, changes)


@router.post('/{question_id}/approve')
def approveQuestion(question_id: str, admin=Depends(get_current_admin)):
    return _change_status(question_id, "approved")


@router.post('/{question_id}/reject')
def rejectQuestion(question_id: str, request: RejectQuestionRequest, admin=Depends(get_current_admin)):
    return _change_status(question_id, "rejected", request.note)


def _change_status(question_id: str, status: str, note: str | None = None):
    question = store.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    if question["status"] == "published":
        raise HTTPException(status_code=400, detail="Question is already published")
    return store.set_status(question_id, status, note)


# Sends approved questions to Eigen's questions + answers tables (students see them).
# Without SUPABASE_SERVICE_KEY they are only marked published in the local file.
@router.post('/publish')
def publishApproved(admin=Depends(get_current_admin)):
    push = eigen_db.insert_question if eigen_db.has_service_key() else None
    result = store.publish_approved(push)
    return {
        "published_count": len(result["published"]),
        "published": [{"id": q["id"], "eigen_question_id": q.get("eigen_question_id")} for q in result["published"]],
        "failed": result["failed"],
        "saved_to_eigen": push is not None,
    }
