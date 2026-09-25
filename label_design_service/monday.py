"""Minimal Monday GraphQL client — stdlib only, retries on timeouts and
complexity/rate-limit errors.

Monday answers HTTP 200 with an `errors` array for a rejected mutation, so
the status code alone would report success; those surface as RuntimeError.
"""
import json
import time
import urllib.error
import urllib.request

API_VERSION = "2024-10"


class Monday:
    def __init__(self, api_key):
        self.api_key = api_key

    def __call__(self, query, variables=None, tries=5):
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        for attempt in range(tries):
            req = urllib.request.Request("https://api.monday.com/v2", data=payload, method="POST",
                                         headers={"Authorization": self.api_key,
                                                  "Content-Type": "application/json",
                                                  "API-Version": API_VERSION})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                # 4xx other than 429 won't get better by retrying (403 = the
                # token's seat can't write this board).
                if (e.code < 500 and e.code != 429) or attempt == tries - 1:
                    raise RuntimeError(f"Monday HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
                time.sleep(5 * (attempt + 1))
                continue
            except (urllib.error.URLError, TimeoutError):
                if attempt == tries - 1:
                    raise
                time.sleep(5 * (attempt + 1))
                continue
            errors = body.get("errors") or ([body] if "error_message" in body else None)
            if errors:
                text = json.dumps(errors)
                if ("Complexity" in text or "rate limit" in text.lower()) and attempt < tries - 1:
                    time.sleep(30)
                    continue
                raise RuntimeError("Monday API error: " + text)
            return body["data"]
