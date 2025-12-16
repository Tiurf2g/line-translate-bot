from fastapi import FastAPI, Request, Form
from webhook import admin_del as _admin_del

app = FastAPI()

@app.post("/")
def delete(request: Request, bucket: str = Form(...), k: str = Form(...)):
    return _admin_del(request, bucket=bucket, k=k)
