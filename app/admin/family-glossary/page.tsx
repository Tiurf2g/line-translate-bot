"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

type Entry = { zh: string; vi: string; tags?: string[]; note?: string | null };

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        borderRadius: 18,
        border: "1px solid rgba(255,255,255,0.14)",
        background: "rgba(255,255,255,0.06)",
        padding: 14,
        backdropFilter: "blur(10px)",
      }}
    >
      <div style={{ fontWeight: 950, fontSize: 14, marginBottom: 10, color: "rgba(255,255,255,0.92)" }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function btnStyle(kind: "pri" | "sec" | "danger" = "sec"): React.CSSProperties {
  const base: React.CSSProperties = {
    height: 40,
    padding: "0 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.18)",
    background: "rgba(255,255,255,0.10)",
    color: "rgba(255,255,255,0.92)",
    fontWeight: 950,
    fontSize: 13,
    cursor: "pointer",
  };
  if (kind === "pri") return { ...base, border: "1px solid rgba(34,197,94,0.35)", background: "rgba(34,197,94,0.14)" };
  if (kind === "danger")
    return { ...base, border: "1px solid rgba(251,113,133,0.35)", background: "rgba(251,113,133,0.14)" };
  return base;
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  height: 40,
  padding: "0 12px",
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.16)",
  background: "rgba(0,0,0,0.18)",
  color: "rgba(255,255,255,0.92)",
  outline: "none",
  boxSizing: "border-box",
  fontSize: 14,
  fontWeight: 800,
};

const smallLabel: React.CSSProperties = { fontSize: 12, color: "rgba(255,255,255,0.65)", marginBottom: 6 };

export default function FamilyGlossaryAdmin() {
  const [pin, setPin] = useState<string>(() =>
    typeof window === "undefined" ? "" : localStorage.getItem("ADMIN_PIN") || ""
  );
  const [showPin, setShowPin] = useState(false);

  const [items, setItems] = useState<Entry[]>([]);
  const [okMsg, setOkMsg] = useState<string>("");
  const [errMsg, setErrMsg] = useState<string>("");

  // add/update
  const [zh, setZh] = useState("");
  const [vi, setVi] = useState("");
  const [tags, setTags] = useState("");
  const [note, setNote] = useState("");

  // import
  const [importText, setImportText] = useState(`[
  { "zh": "晚安", "vi": "ngủ ngon nha", "tags": ["family"] },
  { "zh": "健保卡", "vi": "thẻ bảo hiểm y tế", "tags": ["medical"], "note": "固定這樣翻" }
]`);

  // search
  const [q, setQ] = useState("");

  // inline edit (right click)
  const [editRow, setEditRow] = useState<number | null>(null);
  const [editField, setEditField] = useState<keyof Entry | "tagsText" | null>(null);
  const [editValue, setEditValue] = useState<string>("");
  const editRef = useRef<HTMLInputElement | null>(null);

  function savePinToLocal() {
    if (typeof window !== "undefined") localStorage.setItem("ADMIN_PIN", pin);
  }

  async function apiGet() {
    setErrMsg("");
    setOkMsg("");
    savePinToLocal();
    const r = await fetch("/api/admin/family-glossary", {
      method: "GET",
      headers: { "x-admin-pin": pin, "cache-control": "no-store" },
      cache: "no-store",
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data?.ok === false) throw new Error(data?.error || `HTTP ${r.status}`);
    const list: Entry[] = data?.glossary || data?.items || data?.data || [];
    setItems(Array.isArray(list) ? list : []);
    setOkMsg(`OK · ${Array.isArray(list) ? list.length : 0} 筆`);
  }

  // 兼容不同後端 action：先用 delete/upsert，若回 400 Unknown action，就 fallback 直接 set 全量
  async function apiPost(body: any) {
    savePinToLocal();
    const r = await fetch("/api/admin/family-glossary", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-pin": pin },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    return { r, data };
  }

  async function refresh() {
    try {
      await apiGet();
    } catch (e: any) {
      setErrMsg(e?.message || String(e));
    }
  }

  function normalizeTags(t: string) {
    return t
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function upsertOne(entry: Entry) {
    setErrMsg("");
    setOkMsg("");
    try {
      // optimistic
      const next = [...items];
      const idx = next.findIndex((x) => x.zh === entry.zh);
      if (idx >= 0) next[idx] = entry;
      else next.unshift(entry);
      setItems(next);

      // try upsert
      let { r, data } = await apiPost({ action: "upsert", item: entry });
      if (!r.ok && (data?.error || "").includes("Unknown action")) {
        // fallback: set all
        ({ r, data } = await apiPost({ action: "set", glossary: next }));
      }
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `HTTP ${r.status}`);

      setOkMsg("已儲存");
      // refresh for truth
      await apiGet().catch(() => {});
    } catch (e: any) {
      setErrMsg(e?.message || String(e));
    }
  }

  async function deleteOne(targetZh: string) {
    if (!confirm(`確定刪除「${targetZh}」？`)) return;
    setErrMsg("");
    setOkMsg("");
    try {
      const next = items.filter((x) => x.zh !== targetZh);
      setItems(next);

      let { r, data } = await apiPost({ action: "delete", zh: targetZh });
      if (!r.ok && (data?.error || "").includes("Unknown action")) {
        ({ r, data } = await apiPost({ action: "set", glossary: next }));
      }
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `HTTP ${r.status}`);

      setOkMsg("已刪除");
      await apiGet().catch(() => {});
    } catch (e: any) {
      setErrMsg(e?.message || String(e));
    }
  }

  async function doImport(mode: "append" | "replace") {
    setErrMsg("");
    setOkMsg("");
    try {
      const parsed = JSON.parse(importText);
      const arr: any[] = Array.isArray(parsed) ? parsed : [];
      let { r, data } = await apiPost({ action: "import", mode, items: arr });
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `HTTP ${r.status}`);
      setOkMsg(`已匯入（${mode}）`);
      await apiGet();
    } catch (e: any) {
      setErrMsg(e?.message || String(e));
    }
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `family_glossary_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function resetAll() {
    if (!confirm("確定清空整個詞庫？")) return;
    setErrMsg("");
    setOkMsg("");
    try {
      let { r, data } = await apiPost({ action: "reset" });
      if (!r.ok && (data?.error || "").includes("Unknown action")) {
        ({ r, data } = await apiPost({ action: "set", glossary: [] }));
      }
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `HTTP ${r.status}`);
      setOkMsg("已清空");
      await apiGet();
    } catch (e: any) {
      setErrMsg(e?.message || String(e));
    }
  }

  function clearForm() {
    setZh("");
    setVi("");
    setTags("");
    setNote("");
  }

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return items;
    return items.filter((it) => {
      const t = [
        it.zh || "",
        it.vi || "",
        (it.tags || []).join(","),
        it.note || "",
      ]
        .join(" ")
        .toLowerCase();
      return t.includes(s);
    });
  }, [items, q]);

  // Right click -> edit a cell
  function beginEdit(rowIndex: number, field: "zh" | "vi" | "tagsText" | "note") {
    const row = filtered[rowIndex];
    const val =
      field === "tagsText" ? (row.tags || []).join(", ") : (row as any)[field] ?? "";
    setEditRow(rowIndex);
    setEditField(field);
    setEditValue(String(val));
    setTimeout(() => editRef.current?.focus(), 0);
  }

  function cancelEdit() {
    setEditRow(null);
    setEditField(null);
    setEditValue("");
  }

  async function commitEdit() {
    if (editRow == null || !editField) return;
    const row = filtered[editRow];
    const next: Entry = {
      zh: row.zh,
      vi: row.vi,
      tags: row.tags || [],
      note: row.note ?? null,
    };

    if (editField === "zh") next.zh = editValue.trim();
    if (editField === "vi") next.vi = editValue.trim();
    if (editField === "note") next.note = editValue.trim() ? editValue.trim() : null;
    if (editField === "tagsText") next.tags = normalizeTags(editValue);

    // 重要：zh 不能空
    if (!next.zh) {
      setErrMsg("zh 不能為空");
      return;
    }

    cancelEdit();
    await upsertOne(next);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main
      style={{
        minHeight: "100vh",
        color: "rgba(255,255,255,0.92)",
        background:
          "radial-gradient(1200px 600px at 20% -10%, rgba(125,211,252,0.22), transparent 55%)," +
          "radial-gradient(900px 500px at 85% 0%, rgba(167,139,250,0.18), transparent 55%)," +
          "linear-gradient(180deg, #0b1220, #0f172a)",
        fontFamily:
          'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Noto Sans TC", Arial, "Apple Color Emoji", "Segoe UI Emoji"',
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 18px 56px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div>
            <div style={{ fontSize: 24, fontWeight: 950 }}>家庭詞庫（繁中 ↔ 越南文）</div>
            <div style={{ marginTop: 6, fontSize: 13, color: "rgba(255,255,255,0.65)", lineHeight: 1.45 }}>
              這裡的詞庫會優先用在翻譯提示裡，讓你家翻譯更像台灣/越南在地講法。<br />
              建議把「固定專有名詞、暱稱、地點、口頭禪、醫療/育兒」先補齊。
            </div>
          </div>

          <div
            style={{
              borderRadius: 999,
              padding: "6px 10px",
              border: "1px solid rgba(255,255,255,0.14)",
              background: "rgba(255,255,255,0.08)",
              color: "rgba(255,255,255,0.86)",
              fontSize: 12,
              fontWeight: 900,
              alignSelf: "center",
            }}
          >
            {okMsg || "—"}
          </div>
        </div>

        {(errMsg || "") && (
          <div
            style={{
              marginTop: 12,
              borderRadius: 16,
              border: "1px solid rgba(251,113,133,0.35)",
              background: "rgba(251,113,133,0.12)",
              padding: 12,
              color: "rgba(255,255,255,0.92)",
              fontSize: 13,
              fontWeight: 900,
              whiteSpace: "pre-wrap",
            }}
          >
            {errMsg}
          </div>
        )}

        {/* 管理權限 */}
        <div style={{ marginTop: 14 }}>
          <Card title="管理權限">
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div style={{ flex: "0 0 320px" }}>
                <div style={smallLabel}>ADMIN PIN</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type={showPin ? "text" : "password"}
                    value={pin}
                    onChange={(e) => setPin(e.target.value)}
                    placeholder="輸入 ADMIN_PIN"
                    autoComplete="off"
                    style={inputStyle}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPin((v) => !v)}
                    title={showPin ? "隱藏 PIN" : "顯示 PIN"}
                    style={{ ...btnStyle(), width: 42, padding: 0 }}
                  >
                    {showPin ? "🙈" : "👁"}
                  </button>
                </div>
              </div>

              <button type="button" onClick={refresh} style={btnStyle()}>
                Refresh
              </button>
              <button type="button" onClick={exportJson} style={btnStyle()}>
                Export JSON
              </button>
              <button type="button" onClick={resetAll} style={btnStyle("danger")}>
                Reset
              </button>

              <div style={{ marginLeft: "auto", fontSize: 12, color: "rgba(255,255,255,0.65)" }}>
                顯示：{filtered.length}/{items.length}
              </div>
            </div>
          </Card>
        </div>

        {/* 新增/更新 + 匯入 */}
        <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <Card title="新增 / 更新（以「繁中」當 key）">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <div style={smallLabel}>繁體中文 (zh)</div>
                <input value={zh} onChange={(e) => setZh(e.target.value)} placeholder="例：貼圖" style={inputStyle} />
              </div>
              <div>
                <div style={smallLabel}>越南文 (vi)</div>
                <input value={vi} onChange={(e) => setVi(e.target.value)} placeholder="例：sticker" style={inputStyle} />
              </div>
              <div>
                <div style={smallLabel}>tags（逗號分隔）</div>
                <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="family, baby, medical, nickname" style={inputStyle} />
              </div>
              <div>
                <div style={smallLabel}>note（可選）</div>
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="例：固定這樣翻" style={inputStyle} />
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() =>
                  upsertOne({
                    zh: zh.trim(),
                    vi: vi.trim(),
                    tags: normalizeTags(tags),
                    note: note.trim() ? note.trim() : null,
                  })
                }
                style={btnStyle("pri")}
              >
                Save
              </button>
              <button type="button" onClick={clearForm} style={btnStyle()}>
                Clear
              </button>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", alignSelf: "center" }}>
                小技巧：先放「專有名詞」最有效（地點、親屬、綽號、藥名、食物名）。
              </div>
            </div>
          </Card>

          <Card title="匯入 JSON">
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginBottom: 8 }}>
              格式：{`[{ zh, vi, tags?, note? }]`}（vi 若空也可自行補上）
            </div>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              style={{
                width: "100%",
                minHeight: 150,
                padding: 12,
                borderRadius: 14,
                border: "1px solid rgba(255,255,255,0.16)",
                background: "rgba(0,0,0,0.18)",
                color: "rgba(255,255,255,0.9)",
                outline: "none",
                resize: "vertical",
                fontSize: 12,
                lineHeight: 1.5,
                boxSizing: "border-box",
              }}
            />
            <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
              <button type="button" onClick={() => doImport("append")} style={btnStyle()}>
                Import (append)
              </button>
              <button type="button" onClick={() => doImport("replace")} style={btnStyle("danger")}>
                Import (replace)
              </button>
            </div>
          </Card>
        </div>

        {/* 查詢 */}
        <div style={{ marginTop: 14 }}>
          <Card title="查詢">
            <div style={smallLabel}>搜尋（繁中/越南文/tags/note）</div>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="例：貼圖 / baby / 50 / về nhà..." style={inputStyle} />
          </Card>
        </div>

        {/* 清單（字體統一、清楚；右鍵編輯；每列刪除） */}
        <div style={{ marginTop: 14 }}>
          <Card title="詞庫清單（右鍵某格可編輯，Enter 立即儲存）">
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
                <thead>
                  <tr>
                    {["繁中 (zh)", "越南文 (vi)", "tags", "note", ""].map((h) => (
                      <th
                        key={h}
                        style={{
                          textAlign: "left",
                          padding: "10px 12px",
                          fontSize: 13,
                          fontWeight: 950,
                          color: "rgba(255,255,255,0.78)",
                          borderBottom: "1px solid rgba(255,255,255,0.14)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {filtered.map((it, i) => {
                    const isRowEditing = editRow === i;

                    const cellTextStyle: React.CSSProperties = {
                      padding: "12px 12px",
                      borderBottom: "1px solid rgba(255,255,255,0.10)",
                      fontSize: 15, // ✅ 統一字體大小
                      fontWeight: 900, // ✅ 統一粗細，清楚
                      color: "rgba(255,255,255,0.92)",
                      whiteSpace: "nowrap",
                    };

                    const cellSubStyle: React.CSSProperties = {
                      padding: "12px 12px",
                      borderBottom: "1px solid rgba(255,255,255,0.10)",
                      fontSize: 14,
                      fontWeight: 850,
                      color: "rgba(255,255,255,0.90)",
                      maxWidth: 420,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    };

                    function renderCell(field: "zh" | "vi" | "tagsText" | "note", value: string, style: React.CSSProperties) {
                      const editingThis = isRowEditing && editField === field;
                      if (!editingThis) {
                        return (
                          <td
                            style={{ ...style, cursor: "context-menu" }}
                            onContextMenu={(e) => {
                              e.preventDefault();
                              beginEdit(i, field);
                            }}
                            title="右鍵編輯，Enter 儲存，Esc 取消"
                          >
                            {value || <span style={{ color: "rgba(255,255,255,0.45)", fontWeight: 800 }}>（空）</span>}
                          </td>
                        );
                      }

                      return (
                        <td style={style}>
                          <input
                            ref={editRef as any}
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") commitEdit();
                              if (e.key === "Escape") cancelEdit();
                            }}
                            onBlur={() => commitEdit()}
                            style={{
                              width: "100%",
                              height: 36,
                              padding: "0 10px",
                              borderRadius: 10,
                              border: "1px solid rgba(255,255,255,0.22)",
                              background: "rgba(0,0,0,0.22)",
                              color: "rgba(255,255,255,0.92)",
                              outline: "none",
                              fontSize: 14,
                              fontWeight: 900,
                              boxSizing: "border-box",
                            }}
                          />
                        </td>
                      );
                    }

                    return (
                      <tr key={it.zh + ":" + i}>
                        {renderCell("zh", it.zh, cellTextStyle)}
                        {renderCell("vi", it.vi, cellTextStyle)}
                        {renderCell("tagsText", (it.tags || []).join(", "), cellSubStyle)}
                        {renderCell("note", it.note || "", cellSubStyle)}
                        <td style={{ padding: "10px 12px", borderBottom: "1px solid rgba(255,255,255,0.10)", whiteSpace: "nowrap" }}>
                          <button type="button" onClick={() => deleteOne(it.zh)} style={btnStyle("danger")}>
                            刪除
                          </button>
                        </td>
                      </tr>
                    );
                  })}

                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ padding: 14, color: "rgba(255,255,255,0.65)", fontSize: 13 }}>
                        （沒有資料）
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            <div style={{ marginTop: 10, fontSize: 12, color: "rgba(255,255,255,0.65)" }}>
              操作：右鍵某格 → 直接改內容 → Enter 立即儲存（Esc 取消）
            </div>
          </Card>
        </div>
      </div>
    </main>
  );
}
