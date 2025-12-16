from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# 從 api/webhook.py 匯入後台頁面 function
from webhook import admin_page as _admin_page

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def admin(request: Request):
    return _admin_page(request)
