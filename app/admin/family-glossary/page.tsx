"use client";

import React, { useEffect, useMemo, useState } from "react";

type GlossaryEntry = {
  zh: string;
  en: string;
  tags?: string[];
  note?: string | null;
};

function getPin() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("ADMIN_PIN") || "";
}
function setPin(v: string) {
  localStorage.setItem("ADMIN_PIN", v);
}

export default function FamilyGlossaryAdminPage() {
  const [pin, _setPin] = useState("");
  const [rows, setRows] = useState<GlossaryEntry[]>([]);
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");

  const [zh, setZh] = useState("");
  const [en, setEn] = useState("");
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
      const data = await r.json().catch(() => ({}));
      setRows(data.glossary || []);
      setMsg(`OK (${data.count || 0})`);
    } catch (e: any) {
      setMsg(`Load failed: ${e?.message || e}`);
    }
  }

  async function adminPost(payload: any) {
    const r = await fetch("/api/admin/family-glossary", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-pin": pin },
      body: JSON.stringify(payload),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data?.ok === false) throw new Error(data?.error || `HTTP ${r.status}`);
    return data;
  }

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter(
      (r) => (r.zh || "").toLowerCase().includes(s) || (r.en || "").toLowerCase().includes(s)
    );
  }, [rows, q]);

  return (
    <div style={{ padding: 16, maxWidth: 980, margin: "0 auto", fontFamily: "ui-sans-serif, system-ui" }}>
      <h1 style={{ fontSize: 22, fontWeight: 800 }}>Family Glossary Admin</h1>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
        <input
          value={pin}
          onChange={(e) => {
            _setPin(e.target.value);
            setPin(e.target.value);
          }}
          placeholder="ADMIN PIN"
          style={{ padding: 8, width: 180 }}
        />
        <button onClick={refresh} style={{ padding: "8px 12px" }}>Refresh</button>
        <button
          onClick={async () => {
            if (!confirm("確定清空整個 Family Glossary？")) return;
            const r = await adminPost({ action: "reset" });
            setMsg(JSON.stringify(r));
            await refresh();
          }}
          style={{ padding: "8px 12px" }}
        >
          Reset
        </button>
        <div style={{ marginLeft: "auto", color: "#555" }}>{msg}</div>
      </div>

      <hr style={{ margin: "16px 0" }} />

      <h2 style={{ fontSize: 16, fontWeight: 700 }}>Upsert（以 zh 當 key）</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
        <input value={zh} onChange={(e) => setZh(e.target.value)} placeholder="zh（原文）" style={{ padding: 8 }} />
        <input value={en} onChange={(e) => setEn(e.target.value)} placeholder="en（翻譯）" style={{ padding: 8 }} />
        <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tags（逗號分隔，可空白）" style={{ padding: 8 }} />
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="note（備註，可空白）" style={{ padding: 8 }} />
      </div>

      <div style={{ marginTop: 8 }}>
        <button
          onClick={async () => {
            const entry: GlossaryEntry = {
              zh: zh.trim(),
              en: en.trim(),
              tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
              note: note ? note.trim() : null,
            };
            const r = await adminPost({ action: "upsert", entry });
            setMsg(JSON.stringify(r));
            await refresh();
          }}
          style={{ padding: "8px 12px" }}
        >
          Save
        </button>
      </div>

      <hr style={{ margin: "16px 0" }} />

      <h2 style={{ fontSize: 16, fontWeight: 700 }}>Import JSON</h2>
      <textarea
        value={importText}
        onChange={(e) => setImportText(e.target.value)}
        placeholder='[{"zh":"晚安","en":"Good night","tags":["family"]}]'
        style={{ width: "100%", height: 140, padding: 10, marginTop: 8 }}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button
          onClick={async () => {
            const items: GlossaryEntry[] = JSON.parse(importText);
            const r = await adminPost({ action: "import", mode: "append", items });
            setMsg(JSON.stringify(r));
            await refresh();
          }}
          style={{ padding: "8px 12px" }}
        >
          Import (append)
        </button>

        <button
          onClick={async () => {
            if (!confirm("Replace 會覆蓋整個詞庫，確定？")) return;
            const items: GlossaryEntry[] = JSON.parse(importText);
            const r = await adminPost({ action: "import", mode: "replace", items });
            setMsg(JSON.stringify(r));
            await refresh();
          }}
          style={{ padding: "8px 12px" }}
        >
          Import (replace)
        </button>
      </div>

      <hr style={{ margin: "16px 0" }} />

      <h2 style={{ fontSize: 16, fontWeight: 700 }}>Browse</h2>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="搜尋 zh / en"
        style={{ padding: 8, width: "100%", marginTop: 8 }}
      />

      <div style={{ marginTop: 12, border: "1px solid #ddd", borderRadius: 8, overflow: "hidden" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "240px 1fr 240px 1fr",
            background: "#f6f6f6",
            padding: 10,
            fontWeight: 700,
          }}
        >
          <div>zh</div><div>en</div><div>tags</div><div>note</div>
        </div>

        {filtered.map((r) => (
          <div
            key={r.zh}
            style={{
              display: "grid",
              gridTemplateColumns: "240px 1fr 240px 1fr",
              padding: 10,
              borderTop: "1px solid #eee",
            }}
          >
            <div style={{ fontWeight: 700 }}>{r.zh}</div>
            <div>{r.en}</div>
            <div>{(r.tags || []).join(", ")}</div>
            <div>{r.note || ""}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
