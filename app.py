from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import auth_routes
from routes import questions_routes
from routes import contests_routes, profile_routes

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.include_router(auth_routes.router)
app.include_router(questions_routes.router)
app.include_router(contests_routes.router)
app.include_router(profile_routes.router)


@app.get("/")
def health_check():
    return {"status": "service running"}

# auth and profile table its creation and handling in the context
# daily questions and streak tables
# submission of questions routes and blanks table

