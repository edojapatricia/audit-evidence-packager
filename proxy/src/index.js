// AuditPack free-trial proxy (Cloudflare Worker).
//
// The AI service key lives ONLY here, as the Worker secret ANTHROPIC_API_KEY.
// The desktop app never contains it. The app sends its request here with an
// anonymous install id; this Worker checks the quotas, forces the model and
// token ceiling, adds the key, and streams the answer back.
//
// Quotas use Workers KV, which is not atomic, so limits are "soft": a burst of
// parallel requests can slip a few extra through. For hard guarantees, also set
// a monthly spend limit on the key itself in the provider's console.

const UPSTREAM = "https://api.anthropic.com/v1/messages";
const INSTALL_ID = /^[a-f0-9]{32}$/;

function cfg(env) {
  const n = (v, d) => (Number.isFinite(parseInt(v, 10)) ? parseInt(v, 10) : d);
  return {
    perInstall: n(env.TRIAL_PER_INSTALL, 3),
    perIpDay: n(env.DAILY_PER_IP, 10),
    globalDay: n(env.DAILY_GLOBAL, 150),
    maxTokens: n(env.TRIAL_MAX_TOKENS, 12000),
    maxBody: n(env.MAX_BODY_BYTES, 200000),
    model: env.TRIAL_MODEL || "claude-haiku-5-5",
  };
}

const json = (obj, status = 200, extra = {}) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...extra },
  });

// Same envelope the AI SDKs already know how to read.
const err = (status, type, message) => json({ type: "error", error: { type, message } }, status);

const today = () => new Date().toISOString().slice(0, 10);
const read = async (kv, key) => parseInt((await kv.get(key)) || "0", 10) || 0;
const bump = async (kv, key, by, ttl) => kv.put(key, String(Math.max(0, (await read(kv, key)) + by)), ttl ? { expirationTtl: ttl } : undefined);

function keys(req, id) {
  const ip = req.headers.get("CF-Connecting-IP") || "unknown";
  const d = today();
  return { inst: `i:${id}`, ip: `p:${ip}:${d}`, day: `g:${d}` };
}

async function quota(req, env) {
  const c = cfg(env);
  const id = req.headers.get("X-Install-Id") || "";
  if (!INSTALL_ID.test(id)) return err(400, "invalid_request_error", "Missing or invalid install id.");
  const k = keys(req, id);
  const used = await read(env.TRIAL, k.inst);
  const dayUsed = await read(env.TRIAL, k.day);
  return json({
    limit: c.perInstall,
    remaining: Math.max(0, c.perInstall - used),
    available: dayUsed < c.globalDay,
  });
}

async function messages(req, env) {
  const c = cfg(env);
  if (!env.ANTHROPIC_API_KEY) return err(503, "api_error", "Trial is not configured.");

  const id = req.headers.get("X-Install-Id") || "";
  if (!INSTALL_ID.test(id)) return err(400, "invalid_request_error", "Missing or invalid install id.");

  const len = parseInt(req.headers.get("content-length") || "0", 10);
  if (len > c.maxBody) return err(413, "request_too_large", "Evidence is too large for the free trial.");
  const raw = await req.text();
  if (raw.length > c.maxBody) return err(413, "request_too_large", "Evidence is too large for the free trial.");

  let body;
  try { body = JSON.parse(raw); } catch { return err(400, "invalid_request_error", "Invalid JSON."); }
  const msgs = body && body.messages;
  if (!Array.isArray(msgs) || msgs.length === 0 || msgs.length > 4 ||
      !msgs.every((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string")) {
    return err(400, "invalid_request_error", "Invalid messages.");
  }

  const k = keys(req, id);
  const [inst, ip, day] = await Promise.all([read(env.TRIAL, k.inst), read(env.TRIAL, k.ip), read(env.TRIAL, k.day)]);
  if (inst >= c.perInstall) return err(402, "trial_exhausted", "Free trial used up. Add your own API key in Settings to continue.");
  if (ip >= c.perIpDay) return err(429, "rate_limit_error", "Too many trial requests from this network today. Try again tomorrow or add your own API key.");
  if (day >= c.globalDay) return err(503, "trial_unavailable", "The free trial is at capacity today. Add your own API key in Settings, or try again tomorrow.");

  await Promise.all([bump(env.TRIAL, k.inst, 1), bump(env.TRIAL, k.ip, 1, 172800), bump(env.TRIAL, k.day, 1, 172800)]);

  // Whitelist what is forwarded. The client cannot pick the model, lift the token
  // ceiling, enable tools, or add extra fields.
  const upstreamBody = {
    model: c.model,
    max_tokens: Math.max(256, Math.min(parseInt(body.max_tokens, 10) || c.maxTokens, c.maxTokens)),
    stream: true,
    messages: msgs,
  };
  if (typeof body.system === "string") upstreamBody.system = body.system.slice(0, 120000);

  let up;
  try {
    up = await fetch(UPSTREAM, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify(upstreamBody),
    });
  } catch {
    await bump(env.TRIAL, k.inst, -1);
    return err(502, "api_error", "Could not reach the AI service. Your trial was not used.");
  }

  if (!up.ok) {
    await bump(env.TRIAL, k.inst, -1); // failed calls do not burn a trial use
    return err(502, "api_error", "The AI service returned an error. Your trial was not used.");
  }

  return new Response(up.body, {
    status: 200,
    headers: { "content-type": up.headers.get("content-type") || "text/event-stream", "cache-control": "no-cache" },
  });
}

export async function handle(req, env) {
  const { pathname } = new URL(req.url);
  if (pathname === "/health") return json({ ok: true });
  if (pathname === "/v1/quota" && req.method === "GET") return quota(req, env);
  if (pathname === "/v1/messages" && req.method === "POST") return messages(req, env);
  return json({ error: "not_found" }, 404);
}

export default { fetch: (req, env) => handle(req, env) };
