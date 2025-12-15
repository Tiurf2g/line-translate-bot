from fastapi import FastAPI

app = FastAPI()

@app.get("/api/healthz")
def healthz():
    return {"ok": True}
