# AuditPack free-trial proxy

A small Cloudflare Worker that holds the AI key so the desktop app never has to.

```
AuditPack app  ->  this Worker (holds the key)  ->  AI service
```

The app sends an anonymous install id. The Worker enforces the limits, forces the
model and output ceiling, adds the key, and streams the answer back. It stores only
usage counters in Workers KV, never the evidence text.

## What it protects against

| Risk | Control |
|---|---|
| Key extracted from the installer | The key is not in the installer. It is a Worker secret. |
| One user burning the whole budget | `TRIAL_PER_INSTALL` free analyses per install id |
| A user minting new install ids | `DAILY_PER_IP` per network address per day |
| Total spend runaway | `DAILY_GLOBAL` cap across everyone, per day |
| Expensive requests | Model and `max_tokens` are forced by the Worker; body size capped; tools and extra fields dropped |
| Failed calls wasting a trial | The use is refunded if the AI service errors |

Limits are soft: Workers KV is not atomic, so a burst of parallel requests can slip a
few extra through, and install ids can be forged (it is a trial, not an account).
**Also set a hard monthly spend limit on the key in the AI provider's console.** That
is the real ceiling.

## Deploy (about 10 minutes, free tier)

You need a free Cloudflare account and Node.js.

```bash
cd proxy
npx wrangler login
npx wrangler kv namespace create TRIAL      # copy the printed id into wrangler.toml
npx wrangler secret put ANTHROPIC_API_KEY   # paste the key at the prompt; it is never written to a file
npx wrangler deploy                         # prints https://auditpack-trial-proxy.<you>.workers.dev
```

Use a **new key created just for the trial**, with its own spend limit, so you can
revoke it without touching anything else.

Then put the printed address in `trial_config.py` (`PROXY_URL`) and rebuild the
installer. Check it:

```bash
curl https://auditpack-trial-proxy.<you>.workers.dev/health
```

## Tune it

Edit the `[vars]` block in `wrangler.toml` and run `npx wrangler deploy` again.
`TRIAL_MODEL` decides cost: a smaller model is much cheaper than a flagship one.
Verify the model id you choose is valid for your key before deploying.

## Free-tier limits to know

Workers KV free tier allows roughly 1,000 writes a day, and each analysis uses 3
writes, so expect about 300 trial analyses a day at most. That fits a small launch.
If you outgrow it, move the counters to a Durable Object (atomic) or the paid plan.

## Test

```bash
npm test
```

## Revoking

If the key ever leaks, delete it in the provider's console and run
`npx wrangler secret put ANTHROPIC_API_KEY` with a new one. Installed apps keep working
because they never held the key.
