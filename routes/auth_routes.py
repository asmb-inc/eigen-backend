from fastapi import APIRouter, Depends, HTTPException
from schemas import GetOTPRequest
from supabase_client import supabase

router = APIRouter(prefix = '/auth', tags = ['auth'])


@router.post('/get-otp')
def test(request: GetOTPRequest):
    response = supabase.auth.sign_in_with_otp({
            'phone': f'+91{request.number}',
    })
    print(response)
    return 'test route works'




