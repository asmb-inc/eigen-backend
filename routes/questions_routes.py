from fastapi import APIRouter, Depends, HTTPException
from schemas import GetOTPRequest
from supabase_client import supabase

router = APIRouter(prefix = '/questions', tags = ['auth'])


@router.post('/submit')
def test(request: GetOTPRequest):
   
    pass

