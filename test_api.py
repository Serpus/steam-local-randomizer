"""Quick test of Steam Web API connectivity."""
import json
import time
import urllib.request

URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"

print(f"URL: {URL}")
req = urllib.request.Request(URL, headers={"User-Agent": "steam-local-randomizer/1.1"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"  status: {resp.status}")
        print(f"  headers: {dict(resp.headers)}")
        data = resp.read()
        elapsed = time.time() - t0
        print(f"  read {len(data)} bytes in {elapsed:.1f}s")
        parsed = json.loads(data.decode("utf-8"))
        apps = parsed.get("applist", {}).get("apps", [])
        print(f"  parsed OK, {len(apps)} apps")
        if apps:
            print(f"  sample: {apps[0]}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"  FAIL after {elapsed:.1f}s: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()