# import os
# import jwt
# from supabase_client import supabase
# from fastapi import Depends, HTTPException, status
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# security = HTTPBearer()
# SUPABASE_JWT_SECRET = "GAWG/oqsmOrshsvN2BexWjC6r/JIpH1Wn++fUM0mWRMj/t7/hb3YXJWpX8cS/IRwD/DwyLmBNsA2je0hsBoSQw=="

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase_client import supabase
import os


security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials  # extracts the Bearer token string

    try:
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        return {"id": user.user.id, "email": user.user.email}

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )