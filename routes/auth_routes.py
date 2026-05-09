from fastapi import APIRouter, Depends, HTTPException, File , Form, UploadFile
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
   



@router.post('/profile')
def createProfile(username: str = Form(...), gender: str = Form(...), school: str = Form(...), avatar: UploadFile = File(...) ,user = Depends(get_current_user)):
     
     try:
          avatar_bytes = avatar.read()
          avatar_file_name = f"{uuid.uuid4()}.{avatar.filename.split('.')[-1]}"
          print(avatar_file_name)
          
          response = supabase.storage.from_('avatars').upload(file = avatar_bytes, path = avatar_file_name, file_options={"content-type": avatar.content_type})
          avatar_public_url = supabase.storage.from_('avatars').get_public_url(avatar_file_name)
          print(avatar_public_url)
     
          insertion = (
               supabase.table('profiles').insert({
                    "user_id": user['id'],
                    "username": username,
                    "str": gender,
                    "school": school,
                    "avatar": avatar_public_url          
               }).execute()
          )
          
            
          print(insertion.data[0])
          return insertion.data[0]
          
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))
     
   
      
     
     
     
     
     
        
    




