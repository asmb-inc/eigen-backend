from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from typing import List, Dict, Any
from supabase_client import supabase
from dependencies import get_current_user
from schemas import UpdateSchoolRequest

router = APIRouter(prefix="/profile", tags=["auth"])

@router.get("/streak")
def getProfileStreak(user = Depends(get_current_user)):
    # keep existing RPC call
    response = supabase.rpc(
        "get_current_streak",
        {"p_profile_id": user["id"]} 
    ).execute()

    current_streak = response.data
    return current_streak

    

# STREAK WILL BE CALCULATED FROM 
# SUBMISSIONS
@router.patch('/school')
def updateSchool(request: UpdateSchoolRequest, user=Depends(get_current_user)):
    try:
        supabase.table('profiles').update({'school': request.school}).eq('id', user['id']).execute()
        return {"message": "School updated successfully"}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Could not update school")