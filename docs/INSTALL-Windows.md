# Install AuditPack on Windows

AuditPack maps your audit evidence to ISO 27001:2022 and SOC 2 controls. You do
not need Python or any developer tools.

**Requirements:** Windows 10 or 11 (64-bit), an internet connection, and an
Anthropic API key (see step 3).

## 1. Install

1. Download `AuditPack-Setup-1.0.0.exe`.
2. Double-click it and follow the wizard. It installs for your user only and
   does not need administrator rights.
3. Leave **Launch AuditPack** ticked and click **Finish**.

> **"Windows protected your PC"?** The installer is not yet code-signed, so
> Windows SmartScreen may warn about an unrecognised app. Click **More info**,
> then **Run anyway**. Only do this for a file you downloaded from the official
> project page.

If Microsoft Edge WebView2 is missing, the installer downloads it (about
2 MB) so the app opens in its own window. If that is blocked, AuditPack opens
in your default browser instead and works the same.

## 2. Open it

Use the **AuditPack** shortcut in the Start menu (or on the desktop, if you
ticked that option).

## 3. Add your API key (first run)

AuditPack uses Claude to read your evidence, so it needs your own Anthropic
API key:

1. Create a key at <https://console.anthropic.com/> (API usage is billed to your
   Anthropic account).
2. Paste it into the dialog that opens on first launch and click **Save key**.

The key is encrypted with Windows data protection and stored on your computer
only. Change or remove it any time from **Settings** (bottom-left).

## 4. Use it

1. **Add Evidence:** name the artifact and paste its text (policy excerpts,
   procedures, configuration exports, log excerpts).
2. Choose ISO 27001, SOC 2 or both, then click **Analyze with Claude**.
3. Review the mapped controls, coverage levels and gaps. **Export JSON** saves
   the result.

## Privacy

Evidence you analyse is sent to Anthropic's API using your key. Do not paste
anything you are not allowed to share with that service. AuditPack itself does
not collect or send any data anywhere else.

## Uninstall

**Settings → Apps → Installed apps → AuditPack → Uninstall.** The uninstaller
asks whether to also delete your saved API key and logs (stored in
`%APPDATA%\AuditPack`).

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Nothing happens after launching | Wait up to 20 seconds on first start. Then check the log at `%APPDATA%\AuditPack\logs\app.log`. |
| "No Anthropic API key is set" | Open **Settings** and save your key. |
| Analysis fails with an authentication error | The key is wrong or revoked. Save a new one in **Settings**. |
| Opens in a browser instead of its own window | WebView2 could not be installed. Everything still works; keep the small AuditPack window open while you use it. |
