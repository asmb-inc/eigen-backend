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

class UpdateSchoolRequest(BaseModel):
    school: str


# Admin: AI question generation

class GenerateQuestionsRequest(BaseModel):
    topic: Optional[str] = None          # e.g. "optics", "physics", or a brand-new topic
    all_references: bool = False         # generate from every existing Eigen question
    count: int = 3                       # per topic, or per reference when all_references is true
    difficulty: int = 800                # only used for a topic with no existing question

class AnswerItem(BaseModel):
    blank_order: int
    value: float

class UpdateGeneratedQuestionRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    blanks_count: Optional[int] = None
    answers: Optional[List[AnswerItem]] = None
    topics: Optional[str] = None
    difficulty: Optional[int] = None
    explanation: Optional[str] = None

class RejectQuestionRequest(BaseModel):
    note: Optional[str] = None
