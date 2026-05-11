from fastapi import APIRouter, Depends, HTTPException
from schemas import GetOTPRequest
from supabase_client import supabase
from dependencies import get_current_user

import uuid


router = APIRouter(prefix = '/auth', tags = ['auth'])



# routes for sign in or sign up 


@router.get("/profile")
def get_profile(user=Depends(get_current_user)):
    response = (
        supabase
        .table("profiles")
        .select("*")
        .eq("id", user["id"])
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail="Profile not found"
        )
        
    profile = response.data[0]
    profile["email"] = user["email"]

    return profile
   



    




