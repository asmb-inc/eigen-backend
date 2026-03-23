import os
import jwt
from supabase_client import supabase
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()
SUPABASE_JWT_SECRET = "GAWG/oqsmOrshsvN2BexWjC6r/JIpH1Wn++fUM0mWRMj/t7/hb3YXJWpX8cS/IRwD/DwyLmBNsA2je0hsBoSQw=="

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )

        resp = supabase.table('profiles').select('*').eq('user_id', payload['sub']).execute()
        # profile will be unavailabe only for the firts time route 
        # that route is the profile creation route itself
        return {
            "id": payload["sub"],          # Supabase user ID
            "email": payload.get("email"),
            # "display_name": payload.get('full_name'),
            "role": payload.get("role"),
            'profile_id': (resp.data[0]['id']) if (resp.data) else (-1)
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
