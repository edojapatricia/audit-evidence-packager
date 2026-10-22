import test from "node:test";
import assert from "node:assert/strict";
import { handle } from "../src/index.js";

const ID = "a".repeat(32);

function kv() {
  const m = new Map();
  return { get: async (k) => m.get(k) ?? null, put: async (k, v) => void m.set(k, v), _m: m };
}
const env = (over = {}) => ({ TRIAL: kv(), ANTHROPIC_API_KEY: "sk-ant-SECRET-test", ...over });
const post = (body, headers = {}) =>
  new Request("https://p.test/v1/messages", {
    method: "POST",
    headers: { "content-type": "application/json", "X-Install-Id": ID, "CF-Connecting-IP": "1.2.3.4", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
const good = { model: "claude-opus-4-7", max_tokens: 99999, thinking: { type: "adaptive" }, system: "sys",
  messages: [{ role: "user", content: "hi" }], tools: [{ name: "x" }] };

let upstreamCalls;
function mockUpstream(ok = true) {
  upstreamCalls = [];
  globalThis.fetch = async (url, init) => {
    upstreamCalls.push({ url, init });
    return ok ? new Response("data: {}\n\n", { status: 200, headers: { "content-type": "text/event-stream" } })
              : new Response("boom", { status: 500 });
  };
}

test("forwards a whitelisted body with the secret key and a forced model/ceiling", async () => {
  mockUpstream();
  const e = env();
  const r = await handle(post(good), e);
  assert.equal(r.status, 200);
  const sent = JSON.parse(upstreamCalls[0].init.body);
  assert.equal(sent.model, "claude-haiku-5-5");           // client's model ignored
  assert.equal(sent.max_tokens, 12000);                    // ceiling enforced
  assert.equal(sent.stream, true);
  assert.equal("tools" in sent, false);                    // extras dropped
  assert.equal("thinking" in sent, false);
  assert.equal(upstreamCalls[0].init.headers["x-api-key"], "sk-ant-SECRET-test");
});

test("the secret key never appears in a response to the client", async () => {
  mockUpstream(false);
  const r = await handle(post(good), env());
  const text = await r.text();
  assert.equal(text.includes("SECRET"), false);
});

test("per-install quota: 3 succeed, the 4th is 402 trial_exhausted", async () => {
  mockUpstream();
  const e = env();
  for (let i = 0; i < 3; i++) assert.equal((await handle(post(good), e)).status, 200);
  const r = await handle(post(good), e);
  assert.equal(r.status, 402);
  assert.equal((await r.json()).error.type, "trial_exhausted");
  assert.equal(upstreamCalls.length, 3);                   // 4th never reached the AI service
});

test("a failed upstream call refunds the trial use", async () => {
  mockUpstream(false);
  const e = env();
  assert.equal((await handle(post(good), e)).status, 502);
  const q = await (await handle(new Request("https://p.test/v1/quota", { headers: { "X-Install-Id": ID } }), e)).json();
  assert.equal(q.remaining, 3);
});

test("per-IP daily limit applies across different install ids", async () => {
  mockUpstream();
  const e = env({ DAILY_PER_IP: "2" });
  for (let i = 0; i < 2; i++) assert.equal((await handle(post(good, { "X-Install-Id": String(i).repeat(32) }), e)).status, 200);
  assert.equal((await handle(post(good, { "X-Install-Id": "9".repeat(32) }), e)).status, 429);
});

test("global daily cap stops everyone with 503", async () => {
  mockUpstream();
  const e = env({ DAILY_GLOBAL: "1" });
  assert.equal((await handle(post(good), e)).status, 200);
  const r = await handle(post(good, { "X-Install-Id": "b".repeat(32), "CF-Connecting-IP": "9.9.9.9" }), e);
  assert.equal(r.status, 503);
});

test("rejects bad install id, bad JSON, bad messages, oversize body", async () => {
  mockUpstream();
  const e = env();
  assert.equal((await handle(post(good, { "X-Install-Id": "nope" }), e)).status, 400);
  assert.equal((await handle(post("{not json"), e)).status, 400);
  assert.equal((await handle(post({ messages: [] }), e)).status, 400);
  assert.equal((await handle(post({ messages: [{ role: "system", content: "x" }] }), e)).status, 400);
  assert.equal((await handle(post({ messages: [{ role: "user", content: "x".repeat(300000) }] }), e)).status, 413);
  assert.equal(upstreamCalls.length, 0);
});

test("fails closed when the secret is not configured", async () => {
  mockUpstream();
  const r = await handle(post(good), env({ ANTHROPIC_API_KEY: undefined }));
  assert.equal(r.status, 503);
});

test("unknown routes are 404", async () => {
  assert.equal((await handle(new Request("https://p.test/admin"), env())).status, 404);
});
