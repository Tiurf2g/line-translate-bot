from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def healthz():
    return {"ok": True}
