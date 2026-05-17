import json
import os
from flask import Flask, request, jsonify, Response, send_from_directory
import anthropic
from controls_data import build_controls_reference

app = Flask(__name__, static_folder=None)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

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
    return send_from_directory(".", "index.html")


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

    def generate():
        try:
            with client.messages.stream(
                model="claude-opus-4-7",
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield sse({"type": "text", "content": text})
            yield sse({"type": "done"})
        except Exception as exc:
            yield sse({"type": "error", "message": str(exc)})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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

    def generate():
        try:
            with client.messages.stream(
                model="claude-opus-4-7",
                max_tokens=32000,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield sse({"type": "text", "content": text})
            yield sse({"type": "done"})
        except Exception as exc:
            yield sse({"type": "error", "message": str(exc)})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
