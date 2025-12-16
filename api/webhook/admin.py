from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/")
def admin():
    return HTMLResponse("""
    <h2>ADMIN ALIVE</h2>
    <p>If you see this, routing & function are OK.</p>
    """)
