from fastapi import FastAPI

app = FastAPI(title="ContextForge API")


@app.get("/")
def home():
    return {"message": "ContextForge backend is running!"}