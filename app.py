from fastapi import FastAPI

app = FastAPI()


@app.get('/test')
def hello():
    return 'welcome to battlon backend'
 
