"""Where the free-trial proxy lives.

The proxy URL is public information (it is just an address). The AI key is NOT
here or anywhere in the app: it is stored as a secret on the proxy.

Set PROXY_URL to your deployed Worker address before building the installer,
for example "https://auditpack-trial-proxy.<your-subdomain>.workers.dev".
Leave it empty to disable the free trial (users must add their own key).
The AUDITPACK_PROXY_URL environment variable overrides this value.
"""

PROXY_URL = ""
