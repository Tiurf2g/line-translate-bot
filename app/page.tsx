"use client";

import React, { useEffect, useMemo, useState } from "react";

type StatusResp = {
  ok: boolean;
  time?: string;
  env?: Record<string, any>;
  links?: { webhook?: string; admin?: string };
};

type WebhookResp = Record<string, any>;

function Chip({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px",
        borderRadius: 999,
        border: "1px solid rgba(255,255,255,0.16)",
        background: ok ? "rgba(52,211,153,0.16)" : "rgba(251,113,133,0.14)",
        color: "rgba(255,255,255,0.92)",
        fontSize: 12,
        fontWeight: 800,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 999,
          background: ok ? "rgba(52,211,153,1)" : "rgba(251,113,133,1)",
          display: "inline-block",
        }}
      />
      {label}
    </span>
  );
}

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
      <div style={{ fontWeight: 900, fontSize: 14, marginBottom: 10, color: "rgba(255,255,255,0.92)" }}>{title}</div>
      {children}
    </div>
  );
}

export default function Home() {
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [webhook, setWebhook] = useState<WebhookResp | null>(null);
  const [err, setErr] = useState<string>("");

  // ✅ 一鍵測試翻譯（不送 LINE）
  const [pin, setPin] = useState<string>(() => (typeof window === "undefined" ? "" : localStorage.getItem("ADMIN_PIN") || ""));
  const [testInput, setTestInput] = useState("");
  const [testDir, setTestDir] = useState<"auto" | "zh2vi" | "vi2zh">("auto");
  const [testOut, setTestOut] = useState("");
  const [testErr, setTestErr] = useState("");
  const [testing, setTesting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    if (refreshing) return;
    setRefreshing(true);
    setErr("");

    const ts = Date.now();
    const init: RequestInit = { cache: "no-store", headers: { "cache-control": "no-store" } };

    try {
      const r1 = await fetch(`/api/status?ts=${ts}`, init);
      const s = (await r1.json().catch(() => ({}))) as StatusResp;
      setStatus(s);
      if (!r1.ok || s?.ok === false) throw new Error((s as any)?.error || `HTTP ${r1.status}`);
    } catch (e: any) {
      setErr(`Status API failed: ${e?.message || String(e)}`);
    }

    try {
      const r2 = await fetch(`/api/line/webhook?ts=${ts}`, init);
      const w = (await r2.json().catch(() => ({}))) as WebhookResp;
      setWebhook(w);
    } catch {
      // webhook GET 不一定有 JSON（看你實作），失敗也不要緊
      setWebhook({ ok: false, note: "GET /api/line/webhook did not return JSON" });
    } finally {
      setRefreshing(false);
    }
  }

  async function runTest() {
    setTesting(true);
    setTestErr("");
    setTestOut("");
    try {
      if (typeof window !== "undefined") localStorage.setItem("ADMIN_PIN", pin);

      const r = await fetch("/api/test-translate", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-admin-pin": pin },
        body: JSON.stringify({ text: testInput, direction: testDir }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || (data as any)?.ok === false) throw new Error((data as any)?.error || `HTTP ${r.status}`);

      // ✅ 相容不同回傳欄位：translated / output / text
      setTestOut((data as any).translated || (data as any).output || (data as any).text || "");
    } catch (e: any) {
      setTestErr(e?.message || String(e));
    } finally {
      setTesting(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const env = status?.env || {};
  const last = useMemo(() => {
    if (!status?.time) return "—";
    const d = new Date(status.time);
    return isNaN(d.getTime()) ? status.time : d.toLocaleString();
  }, [status?.time]);

  const links = status?.links || { webhook: "/api/line/webhook", admin: "/admin/family-glossary" };

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
      <div style={{ maxWidth: 1040, margin: "0 auto", padding: "28px 18px 56px" }}>
        <div style={{ display: "flex", gap: 14, alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 24, fontWeight: 950, letterSpacing: 0.2 }}>LINE Translate Bot · 狀態頁</div>
            <div style={{ marginTop: 6, fontSize: 13, color: "rgba(255,255,255,0.65)", lineHeight: 1.45 }}>
              這頁只顯示「是否載入成功」，不會顯示任何 Key。<br />
              最重要的：Webhook 活著、Token 有載入、OpenAI 有載入。
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span
              style={{
                fontSize: 12,
                padding: "6px 10px",
                borderRadius: 999,
                background: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.12)",
                color: "rgba(255,255,255,0.7)",
              }}
            >
              Last refresh: {last}
            </span>
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              style={{
                cursor: refreshing ? "not-allowed" : "pointer",
                opacity: refreshing ? 0.65 : 1,
                borderRadius: 12,
                padding: "10px 12px",
                border: "1px solid rgba(255,255,255,0.18)",
                background: "rgba(255,255,255,0.10)",
                color: "rgba(255,255,255,0.92)",
                fontWeight: 900,
                fontSize: 13,
              }}
            >
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {err ? (
          <div
            style={{
              marginTop: 14,
              borderRadius: 16,
              border: "1px solid rgba(251,113,133,0.35)",
              background: "rgba(251,113,133,0.12)",
              padding: 12,
              color: "rgba(255,255,255,0.9)",
              fontSize: 13,
              fontWeight: 700,
              whiteSpace: "pre-wrap",
            }}
          >
            {err}
          </div>
        ) : null}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 14 }}>
          <Card title="核心服務狀態">
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Chip ok={Boolean(status?.ok)} label="Status API" />
              <Chip ok={Boolean(webhook && (webhook.ok === true || (webhook as any).hint))} label="Webhook GET" />
              <Chip ok={Boolean(env.OPENAI_API_KEY)} label="OpenAI key loaded" />
              <Chip ok={Boolean(env.LINE_CHANNEL_ACCESS_TOKEN)} label="LINE token loaded" />
              <Chip ok={Boolean(env.LINE_CHANNEL_SECRET)} label="LINE secret loaded" />
            </div>

            <div style={{ marginTop: 12, fontSize: 12, color: "rgba(255,255,255,0.68)", lineHeight: 1.5 }}>
              Webhook POST 是否正常：以 LINE Developers 的 Verify 成功為準（你已經 OK）。<br />
              群組翻譯是否正常：以群組實測為準。
            </div>
          </Card>

          <Card title="資料與後台">
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Chip ok={Boolean(env.KV_REST_API_URL)} label="KV URL loaded" />
              <Chip ok={Boolean(env.KV_REST_API_TOKEN)} label="KV token loaded" />
              <Chip ok={Boolean(env.ADMIN_PIN)} label="Admin PIN loaded" />
              <Chip ok={(env.FAMILY_GROUP_IDS_count || 0) > 0} label={`Family groups: ${env.FAMILY_GROUP_IDS_count || 0}`} />
            </div>

            <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <a
                href={links.webhook || "/api/line/webhook"}
                style={{
                  textDecoration: "none",
                  borderRadius: 12,
                  padding: "10px 12px",
                  border: "1px solid rgba(125,211,252,0.38)",
                  background: "rgba(125,211,252,0.14)",
                  color: "rgba(255,255,255,0.95)",
                  fontWeight: 900,
                  fontSize: 13,
                }}
              >
                Open Webhook
              </a>

              <a
                href={links.admin || "/admin/family-glossary"}
                style={{
                  textDecoration: "none",
                  borderRadius: 12,
                  padding: "10px 12px",
                  border: "1px solid rgba(167,139,250,0.38)",
                  background: "rgba(167,139,250,0.14)",
                  color: "rgba(255,255,255,0.95)",
                  fontWeight: 900,
                  fontSize: 13,
                }}
              >
                Open Admin
              </a>

              <a
                href={"/api/family-glossary?force=true"}
                style={{
                  textDecoration: "none",
                  borderRadius: 12,
                  padding: "10px 12px",
                  border: "1px solid rgba(34,197,94,0.35)",
                  background: "rgba(34,197,94,0.12)",
                  color: "rgba(255,255,255,0.95)",
                  fontWeight: 900,
                  fontSize: 13,
                }}
              >
                Init/Check Glossary
              </a>
            </div>

            <div style={{ marginTop: 10, fontSize: 12, color: "rgba(255,255,255,0.68)", lineHeight: 1.5 }}>
              小提醒：這頁只顯示 true/false，不會洩漏任何 key。
            </div>
          </Card>
        </div>

        {/* ✅ 一鍵測試翻譯 */}
        <div style={{ marginTop: 14 }}>
          <Card title="一鍵測試翻譯（不送 LINE）">
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ flex: 1, minWidth: 240 }}>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginBottom: 6 }}>ADMIN PIN（保護測試 API，避免被外面刷）</div>
                <input
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="輸入 ADMIN_PIN"
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    borderRadius: 12,
                    border: "1px solid rgba(255,255,255,0.16)",
                    background: "rgba(0,0,0,0.18)",
                    color: "rgba(255,255,255,0.92)",
                    outline: "none",
                  }}
                />
              </div>

              <div style={{ minWidth: 160 }}>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginBottom: 6 }}>方向</div>
                <select
                  value={testDir}
                  onChange={(e) => setTestDir(e.target.value as any)}
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    borderRadius: 12,
                    border: "1px solid rgba(255,255,255,0.16)",
                    background: "rgba(0,0,0,0.18)",
                    color: "rgba(255,255,255,0.92)",
                    outline: "none",
                  }}
                >
                  <option value="auto">自動判斷</option>
                  <option value="zh2vi">繁中 → 越南文</option>
                  <option value="vi2zh">越南文 → 繁中</option>
                </select>
              </div>

              <div style={{ minWidth: 120 }}>
                <button
                  type="button"
                  onClick={runTest}
                  disabled={testing}
                  style={{
                    cursor: testing ? "not-allowed" : "pointer",
                    width: "100%",
                    borderRadius: 12,
                    padding: "10px 12px",
                    border: "1px solid rgba(255,255,255,0.18)",
                    background: "rgba(255,255,255,0.10)",
                    color: "rgba(255,255,255,0.92)",
                    fontWeight: 900,
                    fontSize: 13,
                    opacity: testing ? 0.65 : 1,
                  }}
                >
                  {testing ? "測試中…" : "測試翻譯"}
                </button>
              </div>
            </div>

            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginBottom: 6 }}>輸入</div>
              <textarea
                value={testInput}
                onChange={(e) => setTestInput(e.target.value)}
                placeholder="輸入你要測的句子（不會送到 LINE）"
                style={{
                  width: "100%",
                  minHeight: 90,
                  padding: "10px 12px",
                  borderRadius: 12,
                  border: "1px solid rgba(255,255,255,0.16)",
                  background: "rgba(0,0,0,0.18)",
                  color: "rgba(255,255,255,0.92)",
                  outline: "none",
                  resize: "vertical",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {testErr ? (
              <div
                style={{
                  marginTop: 10,
                  padding: 10,
                  borderRadius: 12,
                  border: "1px solid rgba(251,113,133,0.35)",
                  background: "rgba(251,113,133,0.12)",
                  fontSize: 12,
                  whiteSpace: "pre-wrap",
                }}
              >
                {testErr}
              </div>
            ) : null}

            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.65)", marginBottom: 6 }}>輸出</div>
              <div
                style={{
                  padding: 12,
                  borderRadius: 12,
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: "rgba(0,0,0,0.22)",
                  minHeight: 48,
                  whiteSpace: "pre-wrap",
                  fontSize: 13,
                }}
              >
                {testOut || "（尚未測試）"}
              </div>
            </div>
          </Card>
        </div>

        <div style={{ marginTop: 14 }}>
          <Card title="原始回傳（除錯用）">
            <pre
              style={{
                margin: 0,
                padding: 12,
                borderRadius: 14,
                background: "rgba(0,0,0,0.22)",
                border: "1px solid rgba(255,255,255,0.10)",
                overflowX: "auto",
                color: "rgba(255,255,255,0.86)",
                fontSize: 12,
                lineHeight: 1.5,
              }}
