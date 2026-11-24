"""Read-only client for Plex's REST API (connect.plex.com), the live source for the picking app.

What it gives (probed 2026-11-20, docs/PICKING_STAGING_APP.md):
- containers: /inventory/v1/inventory-tracking/containers?partId=<uuid> or ?locationId=<uuid>
  (both filters work; partNo, location and masterUnitNo are IGNORED and return all ~66k, 64 MB);
  /containers/{serialNo} for one.
- lots: /inventory/v1/inventory-tracking/lots?partId=<uuid> (bestBy / useBy / sellBy dates).
- jobs: /scheduling/v1/jobs?dueDateBegin=...T00:00:00Z&dueDateEnd=... (full timestamps; status filter ignored).
- locations: /inventory/v1/inventory-definitions/locations.
Live: on 11-20 the API had container changes 4 h newer than our ODBC copy.

Key: env PLEX_API_KEY / PLEX_API_SECRET, else the .env pair PLEX_GCP_API_CONSUMER_KEY / _SECRET,
else Secret Manager plex-api-consumer-key / -secret (company user gcp.odbc.vox). The same key
works on test.connect.plex.com (PLEX_ENV=test). Never logged.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

# At most this many API calls in flight per instance, however many pages load at once (2026-11-23:
# Cloud Run now lets 40 requests in, and 32 parallel calls were no faster than 16 on 11-20).
_PARALLEL = threading.BoundedSemaphore(int(os.environ.get("PICKING_API_PARALLEL", "16")))
BASES = {"test": "https://test.connect.plex.com", "prod": "https://connect.plex.com"}
REPO = Path(__file__).resolve().parents[2]


def _dotenv() -> dict:
    for p in (REPO / ".env", REPO.parent / "plex-to-big-query" / ".env"):
        if p.exists():
            out = {}
            for line in p.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
            return out
    return {}


def api_key() -> tuple[str, str]:
    if os.environ.get("PLEX_API_KEY") and os.environ.get("PLEX_API_SECRET"):
        return os.environ["PLEX_API_KEY"], os.environ["PLEX_API_SECRET"]
    env = _dotenv()
    if env.get("PLEX_GCP_API_CONSUMER_KEY") and env.get("PLEX_GCP_API_CONSUMER_SECRET"):
        return env["PLEX_GCP_API_CONSUMER_KEY"], env["PLEX_GCP_API_CONSUMER_SECRET"]
    from google.cloud import secretmanager
    sm = secretmanager.SecretManagerServiceClient()
    get = lambda n: sm.access_secret_version(request={"name": f"projects/voxdatalake/secrets/{n}/versions/latest"}
                                             ).payload.data.decode("utf-8").strip()
    return get("plex-api-consumer-key"), get("plex-api-consumer-secret")


class PlexApi:
    def __init__(self, env: str | None = None, get=None):
        self.env = (env or os.environ.get("PLEX_ENV", "test")).lower()
        self.base = BASES[self.env]
        self._get = get
        self._key = None
        self._http = None       # one pooled HTTPS session: no new TLS handshake per call (~20% faster, 11-20)

    def _session(self) -> requests.Session:
        if self._http is None:
            s = requests.Session()
            s.mount("https://", HTTPAdapter(pool_connections=2, pool_maxsize=int(os.environ.get("PICKING_API_POOL", "32"))))
            s.headers.update({"X-Plex-Connect-Api-Key": self._key[0], "X-Plex-Connect-Api-Secret": self._key[1],
                              "Accept": "application/json"})
            self._http = s
        return self._http

    def get(self, path: str, **params):
        if params:
            path += ("&" if "?" in path else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if self._get:
            return self._get(path)
        if self._key is None:
            self._key = api_key()
        last = None
        for attempt in range(3):
            try:
                with _PARALLEL:
                    r = self._session().get(self.base + path, timeout=120)
                if r.status_code == 404:
                    return None
                if r.status_code < 500:
                    r.raise_for_status()
                    return r.json() if r.content else None
                last = requests.HTTPError(f"HTTP {r.status_code} from Plex API {path.split('?')[0]}")
            except requests.HTTPError:
                raise
            except (requests.RequestException, ValueError) as e:
                last = e
            time.sleep(2 * (attempt + 1))
        raise last

    # ── typed helpers ──
    def containers_for_part(self, part_id: str) -> list[dict]:
        return self.get("/inventory/v1/inventory-tracking/containers", partId=part_id) or []

    def container(self, serial: str) -> dict | None:
        # safe="": a serial with "/" or "../" must not reach another API path (audit 11-23 #25)
        return self.get(f"/inventory/v1/inventory-tracking/containers/{urllib.parse.quote(serial, safe='')}")

    def containers_at(self, location_id: str) -> list[dict]:
        """Every container at a location, live (the locationId filter works; used to read a pallet's members)."""
        return self.get("/inventory/v1/inventory-tracking/containers", locationId=location_id) or []

    def lots_for_part(self, part_id: str) -> list[dict]:
        return self.get("/inventory/v1/inventory-tracking/lots", partId=part_id) or []

    def jobs_due(self, begin: str, end: str) -> list[dict]:
        return self.get("/scheduling/v1/jobs", dueDateBegin=begin + "T00:00:00Z", dueDateEnd=end + "T00:00:00Z") or []

    def locations(self) -> list[dict]:
        return self.get("/inventory/v1/inventory-definitions/locations") or []
