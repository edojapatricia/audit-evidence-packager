import json
import os
import urllib.request
from flask import Flask, request, jsonify, Response, send_from_directory
import anthropic
import key_store
import trial_config
from controls_data import build_controls_reference
from paths import resource_root

app = Flask(__name__, static_folder=None)

# An ANTHROPIC_API_KEY environment variable wins; otherwise use the key the user
# saved from the in-app Settings dialog (the desktop installer path).
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY") or key_store.load_key() or None
)

NO_KEY_MESSAGE = (
    "No API key is set. Open Settings (bottom-left) and paste your key."
)

# Free trial: with no key of their own, users go through a small proxy that holds
# the real key as a server-side secret. The app only ever knows the proxy address
# and an anonymous install id; no AI key is shipped inside the app.
PROXY_URL = (os.environ.get("AUDITPACK_PROXY_URL") or trial_config.PROXY_URL).rstrip("/")
_trial_client = None


def _get_trial_client():
    global _trial_client
    if _trial_client is None and PROXY_URL:
        _trial_client = anthropic.Anthropic(
            api_key="free-trial",  # placeholder; the proxy supplies the real key
            base_url=PROXY_URL,
            default_headers={"X-Install-Id": key_store.get_install_id()},
            max_retries=0,
        )
    return _trial_client


def _active_client():
    """The user's own key wins; otherwise the free-trial proxy; otherwise None."""
    if client.api_key:
        return client
    return _get_trial_client()


def _trial_status():
    """Remaining free analyses, or None when the trial is not configured."""
    if not PROXY_URL:
        return None
    try:
        req = urllib.request.Request(
            PROXY_URL + "/v1/quota", headers={"X-Install-Id": key_store.get_install_id()}
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {
            "available": bool(data.get("available", True)) and int(data.get("remaining", 0)) > 0,
            "remaining": int(data.get("remaining", 0)),
            "limit": int(data.get("limit", 0)),
        }
    except Exception:
        return {"available": False, "remaining": 0, "limit": 0}


def _error_event(exc: Exception) -> dict:
    """Turn an exception into an SSE error event, keeping trial codes for the UI."""
    event = {"type": "error", "message": str(exc)}
    body = getattr(exc, "body", None)
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        if err.get("message"):
            event["message"] = err["message"]
        if err.get("type") in ("trial_exhausted", "trial_unavailable"):
            event["code"] = err["type"]
    return event


def _stream_analysis(user_message: str, max_tokens: int):
    """SSE response that streams the model's answer for one request."""

    def generate():
        active = _active_client()
        if active is None:
            yield sse({"type": "error", "message": NO_KEY_MESSAGE})
            return
        try:
            with active.messages.stream(
                model="claude-opus-4-7",
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield sse({"type": "text", "content": text})
            yield sse({"type": "done"})
        except Exception as exc:
            yield sse(_error_event(exc))

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


CONTROLS_REFERENCE = build_controls_reference()

# Explicit JSON-only instruction prevents Claude from wrapping output in
# markdown fences or adding explanation text, both of which break the parser.
SYSTEM_PROMPT = f"""You are an expert compliance analyst specializing in ISO 27001:2022 and SOC 2 Type II audits.

CRITICAL OUTPUT RULE: Respond with ONLY a raw JSON object. Do NOT use markdown code fences. Do NOT include any text before or after the JSON. Your entire response must be parseable by JSON.parse(). Start with {{ and end with }}.

Your task: analyze audit evidence artifacts and map them to the relevant compliance controls.

For each piece of evidence:
1. Identify which ISO 27001:2022 controls (A.5–A.8) and/or SOC 2 Trust Service Criteria (CC1–CC9, A1, C1, PI1, P1) are addressed
2. Assess coverage level: Full, Partial, or Insufficient
3. Note gaps and recommendations
4. Provide a concise rationale for each mapping

Control reference:

{CONTROLS_REFERENCE}

Required JSON schema:
{{
  "summary": "Brief overview of the evidence and its compliance relevance",
  "mappings": [
    {{
      "framework": "ISO 27001",
      "control_id": "A.8.15",
      "control_name": "Logging",
      "coverage": "Full",
      "rationale": "Why this evidence maps to this control",
      "gaps": "What additional evidence would strengthen coverage, or empty string"
    }}
  ],
  "overall_coverage": {{
    "iso_27001_controls": ["A.8.15", "A.5.16"],
    "soc2_criteria": ["CC6.1"],
    "risk_level": "Low",
    "recommendations": ["Actionable recommendation 1"]
  }}
}}"""


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.route("/")
def index():
    return send_from_directory(resource_root(), "index.html")


@app.route("/api/settings", methods=["GET"])
def get_settings():
    # Report only whether a key exists; the key itself is never sent back.
    payload = {"api_key_configured": bool(client.api_key)}
    if not payload["api_key_configured"]:
        payload["trial"] = _trial_status()
    return jsonify(payload)


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.get_json(silent=True) or {}
    api_key = str(data.get("api_key", "")).strip()
    if not api_key.startswith("sk-ant-") or len(api_key) < 20 or any(c.isspace() for c in api_key):
        return jsonify({"error": "That doesn't look like a valid API key (it starts with sk-ant-)."}), 400
    key_store.save_key(api_key)
    client.api_key = api_key
    return jsonify({"api_key_configured": True})


@app.route("/api/settings", methods=["DELETE"])
def delete_settings():
    key_store.delete_key()
    client.api_key = os.environ.get("ANTHROPIC_API_KEY") or None
    return get_settings()


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    evidence_name = data.get("evidence_name", "Unnamed Evidence")
    evidence_text = data.get("evidence_text", "")
    frameworks = data.get("frameworks") or ["ISO 27001", "SOC 2"]

    if not evidence_text.strip():
        return jsonify({"error": "Evidence text is required"}), 400

    framework_str = " and ".join(frameworks)
    user_message = (
        f"Analyze this audit evidence artifact and map it to {framework_str} controls.\n\n"
        f"Evidence Name: {evidence_name}\n\n"
        f"Evidence Content:\n{evidence_text}\n\n"
        f"Respond with ONLY the JSON object. No markdown, no explanation."
    )

    return _stream_analysis(user_message, 16000)


@app.route("/api/package", methods=["POST"])
def package():
    data = request.get_json(silent=True) or {}
    evidence_items = data.get("evidence_items") or []
    organization = data.get("organization", "Organization")
    audit_period = data.get("audit_period", "Current Period")
    frameworks = data.get("frameworks") or ["ISO 27001", "SOC 2"]

    if not evidence_items:
        return jsonify({"error": "At least one evidence item is required"}), 400

    items_text = ""
    for i, item in enumerate(evidence_items, 1):
        items_text += f"\n--- Evidence Item {i}: {item.get('name', f'Item {i}')} ---\n"
        items_text += item.get("text", "") + "\n"

    framework_str = " and ".join(frameworks)
    user_message = (
        f"Generate a compliance audit evidence package report for {organization}.\n"
        f"Audit Period: {audit_period}\nFrameworks: {framework_str}\n\n"
        f"Evidence artifacts:\n{items_text}\n\n"
        f"Produce a report that:\n"
        f"1. Summarizes overall compliance posture\n"
        f"2. Maps ALL evidence items to relevant controls\n"
        f"3. Identifies full, partial, and missing coverage\n"
        f"4. Highlights critical pre-audit gaps\n"
        f"5. Provides a prioritized remediation roadmap\n\n"
        f"Respond with ONLY the JSON object. No markdown, no explanation."
    )

    return _stream_analysis(user_message, 32000)


if __name__ == "__main__":
    app.run(debug=os.environ.get("AUDITPACK_DEBUG") == "1", port=5000)
