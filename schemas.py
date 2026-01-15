from pydantic import BaseModel

class GetOTPRequest(BaseModel):
    number: str
    
    