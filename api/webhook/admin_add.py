from fastapi import FastAPI, Request, Form
from webhook import admin_add as _admin_add

app = FastAPI()

@app.post("/")
def add(request: Request, bucket: str = Form(...), k: str = Form(...), v: str = Form(...)):
    return _admin_add(request, bucket=bucket, k=k, v=v)
