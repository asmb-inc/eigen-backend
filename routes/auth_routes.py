from fastapi import APIRouter, Depends, HTTPException
from schemas import GetOTPRequest
from supabase_client import supabase
from dependencies import get_current_user

router = APIRouter(prefix = '/auth', tags = ['auth'])


@router.get('/profile')
def gerProfile(user = Depends(get_current_user)):
     print(user['profile_id'])
     response = (
        supabase
        .table("profiles")
        .select("*")
        .eq("user_id", user['id'])
        .limit(1)
        .execute()
    )

     if response.data:
          return response.data[0]

   
     insert_response = (
          supabase
          .table("profiles")
          .insert({"user_id": user['id']})
          .execute()
     )

     return insert_response.data[0]
          
        
    




