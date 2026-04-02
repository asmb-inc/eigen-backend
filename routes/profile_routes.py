from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from typing import List, Dict, Any
from supabase_client import supabase
from dependencies import get_current_user

router = APIRouter(prefix="/profile", tags=["auth"])

@router.get("/streak")
def getProfileStreak(user = Depends(get_current_user)):
    # keep existing RPC call
    response = supabase.rpc(
        "get_current_streak",
        {"p_profile_id": user["profile_id"]} 
    ).execute()

    current_streak = response.data
    return current_streak
    
    
    

# STREAK WILL BE CALCULATED FROM 
# SUBMISSIONS
