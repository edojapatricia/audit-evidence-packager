# AuditPack — AI-Powered Audit Evidence Packager

Map your compliance artifacts to ISO 27001:2022 and SOC 2 controls in seconds, not days.

---

## What It Does

AuditPack uses Claude (Anthropic's AI) to read your raw audit evidence — policies, procedure documents, configuration exports, audit logs, screenshots descriptions — and automatically maps each artifact to the exact compliance controls it satisfies across ISO 27001:2022 and SOC 2 Type II.

For each piece of evidence it tells you:
- **Which controls are covered** and at what level (Full / Partial / Insufficient)
- **Where the gaps are** and what additional evidence would close them
- **What your overall risk posture is** and a prioritised remediation roadmap

---

## The Problem It Solves

Preparing for an ISO 27001 or SOC 2 audit is expensive and slow. The typical process looks like this:

| Step | Manual approach | Time cost |
|------|----------------|-----------|
| Collect evidence | Spreadsheets, email chains, shared drives | Days |
| Map to controls | Compliance consultant or internal analyst reading each control | Weeks |
| Identify gaps | Cross-reference matrix, manual review | Days |
| Package for auditor | Format, label, organise everything | Days |

For a **mid-size company** this process often takes 4–8 weeks of analyst time and costs £15,000–£50,000 in consulting fees per audit cycle.

For an **SME** with no dedicated compliance team it is frequently impossible without hiring external help — meaning certification is out of reach, and with it, many enterprise sales opportunities.

AuditPack compresses the mapping and gap-analysis phase from weeks to minutes.

---

## Value for Companies

### Enterprise
- **Accelerate audit prep** — reduce the evidence-mapping phase from weeks to hours, freeing your GRC team for higher-value work
- **Consistency** — every artifact is evaluated against the same complete control library (93 ISO 27001:2022 controls, all SOC 2 TSC categories) every time, with no controls accidentally skipped
- **Audit-ready packages** — export structured JSON for ingestion into your GRC platform or to hand directly to your auditor
- **Continuous compliance** — re-analyse updated policies or configurations as they change, not just at audit time

### SMEs and Startups
- **No consultant required for the mapping phase** — SMEs that cannot afford a full-time compliance analyst can produce a credible evidence package independently
- **Faster path to certification** — ISO 27001 or SOC 2 certification opens doors to enterprise customers who require it as a vendor prerequisite; AuditPack removes a major bottleneck
- **Understand your posture before the auditor does** — see exactly which controls are weak before you spend money on a formal audit, so there are no surprises
- **Educate the team** — the rationale and gap explanations double as internal training material that explains *why* each control matters

### Financial impact (illustrative)
| Scenario | Without AuditPack | With AuditPack |
|----------|------------------|---------------|
| SME first-time ISO 27001 prep | £25,000–£40,000 consultant fees | Analyst time only |
| Enterprise annual SOC 2 renewal | 3–4 weeks analyst time | 1–2 days analyst time |
| Gap identification before audit | Discovered during audit (expensive) | Identified pre-audit (cheap to fix) |

---

## Install (Windows)

The easiest way: download **`AuditPack-Setup-1.0.0.exe`** and run it. No Python
needed. See [docs/INSTALL-Windows.md](docs/INSTALL-Windows.md) for the step-by-step
guide. On first launch the app asks for your own Anthropic API key and stores it
encrypted on your machine.

To build the installer yourself, or to run from source, read on.

---

## How to Use It (from source)

### Prerequisites

- Python 3.10 or later
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Install dependencies

```bash
cd audit-evidence-packager
pip install -r requirements.txt
```

### 2. Set your API key

```bash
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Start the server

```bash
python app.py
```

### 4. Open the app

Navigate to **http://localhost:5000** in your browser.

> Do not open `index.html` directly from the filesystem — the API calls require the Flask server to be running.

---

## Workflow

### Analyse a single artifact

1. Click **Add Evidence** in the left panel
2. Give your artifact a descriptive name (e.g. `Access Control Policy v2.3`)
3. Paste the content — policy text, procedure steps, configuration output, log excerpts, or a plain-English description of a screenshot
4. Select the frameworks you are mapping to (ISO 27001, SOC 2, or both)
5. Click **Analyze with Claude**

The right panel streams Claude's analysis in real time and renders:
- An executive summary with overall risk level
- A control mapping grid showing every matched control, its coverage level, and the rationale
- A gap callout on any partially-covered control
- A prioritised recommendations list

### Build a full compliance package

1. For each artifact, click **Save to Library** instead of (or after) analysing it
2. Switch to the **Library** tab to review and manage your collection
3. Click **Package All & Generate Report** to have Claude analyse every artifact together and produce a consolidated compliance report
4. Click **Export JSON** to download the full structured report for your records or GRC system

---

## What to Put In As Evidence

AuditPack works with any text-based evidence. Examples by control area:

| Control area | Evidence to paste |
|-------------|-------------------|
| Access control | Excerpts from your access control policy, RBAC matrix, MFA configuration settings |
| Incident response | IR procedure document, incident log template, SLA table |
| Backup & recovery | Backup policy text, RTO/RPO targets, test results summary |
| Vulnerability management | Patch management procedure, scan schedule, remediation SLA table |
| Supplier management | Vendor assessment questionnaire template, due-diligence checklist |
| Physical security | Data centre access policy, visitor log procedure, CCTV policy |
| Logging & monitoring | SIEM configuration description, log retention policy, alerting rules summary |
| Cryptography | Encryption standard document, key management procedure |
| Business continuity | BCP executive summary, test schedule, RTO targets |

---

## Technical Overview

| Layer | Technology |
|-------|-----------|
| AI model | Claude Opus 4.7 (Anthropic) with adaptive thinking |
| Backend | Python / Flask — SSE streaming |
| Frontend | Vanilla HTML/CSS/JS — no build step |
| Control library | 93 ISO 27001:2022 controls (A.5–A.8) + full SOC 2 TSC (CC1–CC9, A1, C1, PI1, P1) |
| Output | Structured JSON — portable to any GRC platform |

The backend streams Claude's response token-by-token over Server-Sent Events so you see progress in real time even for large evidence packages.

---

## Running the Test Suite

```bash
python test_app.py
```

47 tests covering input validation, SSE stream format, Unicode/XSS edge cases, large payloads, the full controls data integrity, and the API-key settings and the encrypted key store.

---

## Project Structure

```
audit-evidence-packager/
├── app.py              # Flask backend — /api/analyze, /api/package, /api/settings
├── controls_data.py    # ISO 27001:2022 and SOC 2 control definitions
├── key_store.py        # Saves the user's API key (Windows DPAPI-encrypted)
├── paths.py            # Resource/user-data paths that work frozen or from source
├── index.html          # Frontend UI (served by Flask)
├── requirements.txt    # Python dependencies
├── test_app.py         # Test suite (47 tests, no API key needed)
├── desktop/            # Windows installer build (launcher, PyInstaller spec, Inno Setup)
└── docs/               # End-user install guide
```

---

## Building the Windows installer

Requires Windows, Python 3.10–3.13 and [Inno Setup 6](https://jrsoftware.org/isdl.php)
(`winget install JRSoftware.InnoSetup`).

```powershell
powershell -ExecutionPolicy Bypass -File desktopuild_windows.ps1
```

Output in `dist/`:

- `installer/AuditPack-Setup-1.0.0.exe` — the installer to hand to users (~21 MB)
- `AuditPack/` — the application folder
- `AuditPack-windows-portable.zip` — no-install version

How it works: `desktop/launcher.py` serves the Flask app on a private localhost
port with waitress and opens it in a native WebView2 window (falling back to the
default browser). PyInstaller bundles Python and every dependency, so users need
nothing installed. The installer is unsigned, so Windows SmartScreen shows a
warning until it is code-signed.

---

## Limitations

- Evidence must be provided as text. Images and PDFs need to be described or converted to text first.
- The quality of mappings depends on the detail in the evidence provided. Vague inputs produce vague mappings.
- This tool assists the evidence-mapping phase. It does not replace a qualified auditor or guarantee certification.
- API costs apply for each analysis — Opus 4.7 pricing applies per token.
