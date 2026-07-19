import json
import os
import urllib.error
import urllib.request

for v in (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
    "GOOGLE_OAUTH_SCOPES",
):
    print(f"{v}={'set' if os.environ.get(v) else 'empty'}")

uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "")
print(
    "GOOGLE_OAUTH_REDIRECT_URI=canonical_ok"
    if uri == "https://api.krowolf.se/integrations/google_mail/oauth/callback"
    else "GOOGLE_OAUTH_REDIRECT_URI=non_canonical"
)

scopes = os.environ.get("GOOGLE_OAUTH_SCOPES", "")
if scopes and "gmail.send" not in scopes:
    print("GOOGLE_OAUTH_SCOPES=pilot_minimal")
elif scopes:
    print("GOOGLE_OAUTH_SCOPES=includes_send")
else:
    print("GOOGLE_OAUTH_SCOPES=empty")

try:
    urllib.request.urlopen("http://127.0.0.1:8000/integrations/google_mail/oauth/start")
except urllib.error.HTTPError as e:
    print(f"legacy_oauth_start={e.code}")

print("health", urllib.request.urlopen("http://127.0.0.1:8000/health").status)
with open("/app/build-metadata.json", encoding="utf-8") as f:
    print("build_metadata", json.load(f))
