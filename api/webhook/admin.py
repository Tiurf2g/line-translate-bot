import os, base64, json, requests
from typing import Dict, Any
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

KV_REST_API_URL = os.getenv("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN", "")
DICT_KEY = os.getenv("DICT_KEY", "dict_translate_bot_v1")

ADMIN_BASE = "/api/webhook/admin"

def _dict_default() -> Dict[str, Dict[str, str]]:
    return {"tw_to_vn": {}, "vn_to_tw": {}, "replace_out": {}}

def kv_enabled() -> bool:
    return bool(KV_REST_API_URL and KV_REST_API_TOKEN)

def kv_get_dict() -> Dict[str, Dict[str, str]]:
    if not kv_enabled():
        return _dict_default()
    try:
        r = requests.get(
            f"{KV_REST_API_URL}/get/{DICT_KEY}",
            headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"},
            timeout=5,
        )
        raw = r.json().get("result")
        if isinstance(raw, str) and raw:
            d = json.loads(raw)
        elif isinstance(raw, dict):
            d = raw
        else:
            d = _dict_default()
        for k in ("tw_to_vn", "vn_to_tw", "replace_out"):
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
        return d
    except Exception:
        return _dict_default()

def _basic_auth_ok(request: Request) -> bool:
    if not (ADMIN_USER and ADMIN_PASS):
        return False
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        return False
    try:
        b64 = auth.split(" ", 1)[1].strip()
        raw = base64.b64decode(b64).decode("utf-8", errors="ignore")
        user, pw = raw.split(":", 1)
        return user == ADMIN_USER and pw == ADMIN_PASS
    except Exception:
        return False

def _basic_auth_challenge() -> HTMLResponse:
    return HTMLResponse(
        "Unauthorized",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Dictionary Admin"'},
    )

@app.get("/", response_class=HTMLResponse)
def admin_page(request: Request):
    if not _basic_auth_ok(request):
        return _basic_auth_challenge()

    d = kv_get_dict()
    tw_to_vn = d.get("tw_to_vn", {})
    vn_to_tw = d.get("vn_to_tw", {})
    replace_out = d.get("replace_out", {})

    def render_table(title, data):
        rows = "".join([f"<tr><td style='padding:6px'>{k}</td><td style='padding:6px'>{v}</td></tr>" for k, v in data.items()])
        if not rows:
            rows = "<tr><td colspan='2' style='padding:6px;color:#666'>(empty)</td></tr>"
        return f"""
        <h4 style="margin-top:18px">{title}</h4>
        <table border="1" cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%">
          <tr><th style='padding:6px'>Key</th><th style='padding:6px'>Value</th></tr>
          {rows}
        </table>
        """

    warn = ""
    if not kv_enabled():
        warn = "<p style='color:#b00'>⚠️ 尚未設定 Upstash KV（KV_REST_API_URL / KV_REST_API_TOKEN），新增不會永久保存。</p>"

    html = f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Dictionary Admin</title></head>
    <body style="font-family: Arial; padding:16px; max-width:820px; margin:auto">
      <h3>Dictionary Admin</h3>
      {warn}

      <div style="padding:12px; border:1px solid #ddd; border-radius:10px">
        <h4 style="margin-top:0">新增 / 更新詞條</h4>
        <form method="post" action="{ADMIN_BASE}/add">
          <div style="margin:8px 0">
            類型：
            <select name="bucket">
              <option value="tw_to_vn">TW → VN</option>
              <option value="vn_to_tw">VN → TW</option>
              <option value="replace_out">輸出保底替換</option>
            </select>
          </div>
          <div style="margin:8px 0">Key：<input name="k" style="width:70%" /></div>
          <div style="margin:8px 0">Value：<input name="v" style="width:70%" /></div>
          <button type="submit" style="padding:8px 14px">Save</button>
        </form>
      </div>

      <div style="padding:12px; border:1px solid #ddd; border-radius:10px; margin-top:12px">
        <h4 style="margin-top:0">刪除詞條</h4>
        <form method="post" action="{ADMIN_BASE}/del">
          <div style="margin:8px 0">
            類型：
            <select name="bucket">
              <option value="tw_to_vn">TW → VN</option>
              <option value="vn_to_tw">VN → TW</option>
              <option value="replace_out">輸出保底替換</option>
            </select>
          </div>
          <div style="margin:8px 0">Key：<input name="k" style="width:70%" /></div>
          <button type="submit" style="padding:8px 14px">Delete</button>
        </form>
      </div>

      {render_table("TW → VN", tw_to_vn)}
      {render_table("VN → TW", vn_to_tw)}
      {render_table("Replace Output", replace_out)}
    </body></html>
    """
    return HTMLResponse(html, status_code=200)
