from pydantic import BaseModel
from typing import List, Optional
from typing import Dict


class GetOTPRequest(BaseModel):
    number: str
    
    
    
class PostAnswerRequest(BaseModel):
    answers: List[Optional[float]]
    

class SubmitContestRequest(BaseModel):
    answers: Dict[int, List[float]]
    
class GetQuestionByDateString(BaseModel):
    datestring: str
