"use client";

import React, { useEffect, useMemo, useState } from "react";

type GlossaryEntry = {
  zh: string;             // 繁體中文
  vi: string;             // 越南文
  tags?: string[];
  note?: string | null;
  // 兼容舊資料：如果後端回 en，前端也吃得下
  en?: string;
};

function getPin() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("ADMIN_PIN") || "";
}
function setPin(v: string) {
  localStorage.setItem("ADMIN_PIN", v);
}

function normalizeClient(items: GlossaryEntry[]) {
  return (items || [])
    .map((x) => ({
      zh: (x.zh || "").trim(),
      vi: ((x.vi ?? x.en) || "").trim(),
      tags: (x.tags || []).map(String).map((t) => t.trim()).filter(Boolean),
      note: x.note ?? null,
    }))
    .filter((x) => x.zh);
}

export default function FamilyGlossaryAdminPage() {
  const [pin, _setPin] = useState("");
  const [msg, setMsg] = useState("");
  const [rows, setRows] = useState<GlossaryEntry[]>([]);

  const [q, setQ] = useState("");
  const [zh, setZh] = useState("");
  const [vi, setVi] = useState("");
  const [tags, setTags] = useState("");
  const [note, setNote] = useState("");

  const [importText, setImportText] = useState("");

  useEffect(() => {
    const p = getPin();
    _setPin(p);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    setMsg("Loading...");
    try {
      const r = await fetch("/api/family-glossary?force=true", { cache: "no-store" });
      const data = await r.json();
      const list = normalizeClient(data.glossary || []);
      setRows(list);
      setMsg(`OK · ${list.length} 筆`);
    } catch (e: any) {
      setMsg(`Load failed: ${e?.message || String(e)}`);
    }
  }

  async function adminPost(payload: any) {
    const r = await fetch("/api/admin/family-glossary", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-pin": pin },
      body: JSON.stringify(payload),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data?.ok === false) {
      throw new Error(data?.error || `HTTP ${r.status}`);
    }
    return data;
  }

  const filtered = useMemo(() => {
    const keyword = q.trim().toLowerCase();
    if (!keyword) return rows;
    return rows.filter((r) => {
      const hay = `${r.zh} ${r.vi} ${(r.tags || []).join(" ")} ${r.note || ""}`.toLowerCase();
      return hay.includes(keyword);
    });
  }, [rows, q]);

  const countText = useMemo(() => `${filtered.length}/${rows.length}`, [filtered.length, rows.length]);

  function resetForm() {
    setZh("");
    setVi("");
    setTags("");
    setNote("");
  }

  async function onSave() {
    const entry: GlossaryEntry = {
      zh: zh.trim(),
      vi: vi.trim(),
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      note: (note || "").trim() || null,
    };
    if (!entry.zh) return alert("請填「繁中」(zh)");
    if (!entry.vi) return alert("請填「越南文」(vi)");

    const r = await adminPost({ action: "upsert", entry });
    setMsg(`Saved · ${r?.count ?? ""}`);
    resetForm();
    await refresh();
  }

  async function onResetAll() {
    if (!confirm("確定清空整個『家庭詞庫』？這會刪掉所有詞條。")) return;
    const r = await adminPost({ action: "reset" });
    setMsg(`Reset · ${r?.count ?? ""}`);
    await refresh();
  }

  async function onImport(mode: "append" | "replace") {
    try {
      const itemsRaw: GlossaryEntry[] = JSON.parse(importText);
      const items = normalizeClient(itemsRaw);
      if (items.length === 0) return alert("Import 內容是空的或格式不對");
      const r = await adminPost({ action: "import", mode, items });
      setMsg(`Import ${mode} · merged=${r?.count ?? ""} · imported=${r?.imported ?? ""}`);
      await refresh();
    } catch (e: any) {
      alert(`Import JSON 解析失敗：${e?.message || String(e)}`);
    }
  }

  async function onExport() {
    const payload = JSON.stringify(rows, null, 2);
    await navigator.clipboard.writeText(payload);
    setMsg("已複製 JSON 到剪貼簿 ✅");
  }

  return (
    <>
      <style jsx global>{`
        :root {
          --bg1: #0b1220;
          --bg2: #0f172a;
          --card: rgba(255,255,255,0.06);
          --card2: rgba(255,255,255,0.09);
          --border: rgba(255,255,255,0.12);
          --text: rgba(255,255,255,0.92);
          --muted: rgba(255,255,255,0.62);
          --accent: #7dd3fc;
          --accent2: #a78bfa;
          --danger: #fb7185;
          --ok: #34d399;
        }
        body {
          margin: 0;
          color: var(--text);
          background: radial-gradient(1200px 600px at 20% -10%, rgba(125,211,252,0.22), transparent 55%),
                      radial-gradient(900px 500px at 85% 0%, rgba(167,139,250,0.18), transparent 55%),
                      linear-gradient(180deg, var(--bg1), var(--bg2));
          font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Noto Sans TC", Arial, "Apple Color Emoji", "Segoe UI Emoji";
        }
        .wrap { max-width: 1080px; margin: 0 auto; padding: 28px 18px 60px; }
        .topbar { display:flex; gap:14px; align-items:flex-end; justify-content:space-between; margin-bottom: 14px; }
        .title { font-size: 22px; font-weight: 900; letter-spacing: 0.2px; }
        .subtitle { font-size: 13px; color: var(--muted); margin-top: 6px; line-height: 1.4; }
        .pill { font-size: 12px; padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,0.08); border: 1px solid var(--border); color: var(--muted); }
        .grid { display:grid; grid-template-columns: 1.2fr 1fr; gap: 14px; margin-top: 14px; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 14px; backdrop-filter: blur(10px); }
        .card h2 { margin:0 0 10px; font-size: 14px; font-weight: 800; color: rgba(255,255,255,0.88); }
        .row { display:flex; gap: 10px; align-items:center; flex-wrap: wrap; }
        .field { display:flex; flex-direction: column; gap:6px; flex:1; min-width: 180px; }
        .label { font-size: 12px; color: var(--muted); }
        input, textarea {
          width: 100%;
          box-sizing: border-box;
          padding: 10px 12px;
          border-radius: 12px;
          border: 1px solid rgba(255,255,255,0.16);
          background: rgba(0,0,0,0.18);
          color: var(--text);
          outline: none;
        }
        textarea { min-height: 140px; resize: vertical; }
        input:focus, textarea:focus { border-color: rgba(125,211,252,0.55); box-shadow: 0 0 0 3px rgba(125,211,252,0.14); }
        .btn {
          border: 1px solid rgba(255,255,255,0.18);
          background: rgba(255,255,255,0.10);
          color: var(--text);
          padding: 10px 12px;
          border-radius: 12px;
          cursor: pointer;
          font-weight: 700;
          font-size: 13px;
        }
        .btn:hover { background: rgba(255,255,255,0.14); }
        .btn.primary { border-color: rgba(125,211,252,0.42); background: rgba(125,211,252,0.16); }
        .btn.danger { border-color: rgba(251,113,133,0.40); background: rgba(251,113,133,0.14); }
        .btn.ghost { background: transparent; }
        .muted { color: var(--muted); font-size: 12px; }
        .table { margin-top: 14px; overflow: hidden; border-radius: 16px; border: 1px solid var(--border); background: rgba(255,255,255,0.06); }
        .thead, .trow { display:grid; grid-template-columns: 220px 1fr 220px 1fr; gap: 10px; padding: 12px 14px; }
        .thead { background: rgba(0,0,0,0.18); color: rgba(255,255,255,0.78); font-weight: 800; font-size: 12px; }
        .trow { border-top: 1px solid rgba(255,255,255,0.08); align-items: start; }
        .k { font-weight: 900; }
        .tags { color: rgba(255,255,255,0.70); font-size: 12px; }
        .note { color: rgba(255,255,255,0.72); font-size: 12px; white-space: pre-wrap; }
        @media (max-width: 900px) {
          .grid { grid-template-columns: 1fr; }
          .thead, .trow { grid-template-columns: 160px 1fr; }
          .thead div:nth-child(3), .thead div:nth-child(4) { display:none; }
          .trow div:nth-child(3), .trow div:nth-child(4) { display:none; }
        }
      `}</style>

      <div className="wrap">
        <div className="topbar">
          <div>
            <div className="title">家庭詞庫（繁中 ↔ 越南文）</div>
            <div className="subtitle">
              這裡加的詞條會優先用在翻譯提示裡，讓你在家裡聊天更貼近台灣/越南在地講法。
              <br />
              建議把「固定專有名詞、暱稱、站點、模組、常用口頭禪」都放進來。
            </div>
          </div>
          <div className="pill">{msg || "—"}</div>
        </div>

        <div className="card">
          <h2>管理權限</h2>
          <div className="row">
            <div className="field" style={{ maxWidth: 260 }}>
              <div className="label">ADMIN PIN</div>
              <input
                value={pin}
                onChange={(e) => {
                  _setPin(e.target.value);
                  setPin(e.target.value);
                }}
                placeholder="輸入 ADMIN_PIN"
              />
            </div>
            <button className="btn" onClick={refresh}>Refresh</button>
            <button className="btn" onClick={onExport}>Export JSON</button>
            <button className="btn danger" onClick={onResetAll}>Reset</button>
            <div className="muted" style={{ marginLeft: "auto" }}>
              顯示：{countText}
            </div>
          </div>
        </div>

        <div className="grid">
          <div className="card">
            <h2>新增 / 更新（以「繁中」當 key）</h2>
            <div className="row">
              <div className="field">
                <div className="label">繁體中文 (zh)</div>
                <input value={zh} onChange={(e) => setZh(e.target.value)} placeholder="例：50模組 / 健保卡 / 回家洗澡" />
              </div>
              <div className="field">
                <div className="label">越南文 (vi)</div>
                <input value={vi} onChange={(e) => setVi(e.target.value)} placeholder="例：mô-đun 50 / thẻ bảo hiểm y tế / về nhà tắm nha" />
              </div>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <div className="field">
                <div className="label">tags（逗號分隔）</div>
                <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="family, baby, medical, nickname" />
              </div>
              <div className="field">
                <div className="label">note（可選）</div>
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="例：老婆習慣用這個說法 / 固定要這樣翻" />
              </div>
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn primary" onClick={onSave}>Save</button>
              <button className="btn ghost" onClick={resetForm}>Clear</button>
              <div className="muted">小技巧：先放「專有名詞」最有效（站點、模組、綽號、藥名、食物名）。</div>
            </div>
          </div>

          <div className="card">
            <h2>匯入 JSON</h2>
            <div className="muted">
              格式：<code>[{"{zh, vi, tags?, note?}"}]</code>（舊資料如果是 <code>en</code>，也會自動當成 <code>vi</code>）
            </div>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={`[
  { "zh": "晚安", "vi": "ngủ ngon nha", "tags": ["family"] },
  { "zh": "健保卡", "vi": "thẻ bảo hiểm y tế", "tags": ["medical"], "note": "固定這樣翻" }
]`}
              style={{ marginTop: 10 }}
            />
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn" onClick={() => onImport("append")}>Import (append)</button>
              <button className="btn danger" onClick={() => onImport("replace")}>Import (replace)</button>
              <div className="muted">replace 會整個覆蓋，append 會合併（同 zh 以最後一筆為準）。</div>
            </div>
          </div>
        </div>

        <div className="card" style={{ marginTop: 14 }}>
          <h2>查詢</h2>
          <div className="row">
            <div className="field">
              <div className="label">搜尋（繁中/越南文/tags/note）</div>
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="例：健保 / baby / 50 / về nhà ..." />
            </div>
          </div>
        </div>

        <div className="table">
          <div className="thead">
            <div>繁中 (zh)</div>
            <div>越南文 (vi)</div>
            <div>tags</div>
            <div>note</div>
          </div>
          {filtered.map((r) => (
            <div key={r.zh} className="trow">
              <div className="k">{r.zh}</div>
              <div>{(r as any).vi ?? (r as any).en ?? ""}</div>
              <div className="tags">{(r.tags || []).join(", ")}</div>
              <div className="note">{r.note || ""}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
