from pydantic import BaseModel
from typing import List, Optional
class GetOTPRequest(BaseModel):
    number: str
    
    
    
class PostAnswerRequest(BaseModel):
    answers: List[Optional[float]]