"""
Verify Freshdesk V2 API on default subdomain (revelator.freshdesk.com)
per Freshdesk Support guidance that V2 only works on *.freshdesk.com, not vanity URLs.
Also verify actual rate limits and plan tier.
"""
import os
import sys
import json
import time
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path

API_KEY = None

def load_api_key():
    global API_KEY
    API_KEY = os.getenv("FRESHDESK_API_KEY")
    if not API_KEY:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().strip().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    if key.strip() == "FRESHDESK_API_KEY":
                        API_KEY = val.strip()
                        break
    if not API_KEY:
        print("ERROR: No FRESHDESK_API_KEY found")
        sys.exit(1)
    print(f"API Key: {API_KEY[:6]}...{API_KEY[-4:]}")


def test_endpoint(url, label):
    auth = HTTPBasicAuth(API_KEY, "X")
    try:
        resp = requests.get(url, auth=auth, timeout=30)
        headers = {
            "X-RateLimit-Total": resp.headers.get("X-RateLimit-Total", "?"),
            "X-RateLimit-Remaining": resp.headers.get("X-RateLimit-Remaining", "?"),
            "X-RateLimit-Used-CurrentRequest": resp.headers.get("X-RateLimit-Used-CurrentRequest", "?"),
        }
        rate_str = f"[Rate: {headers['X-RateLimit-Remaining']}/{headers['X-RateLimit-Total']}]"

        if resp.status_code == 200:
            data = resp.json()
            count = len(data) if isinstance(data, list) else 1
            print(f"  [200 OK]  {label:<55} {count} records  {rate_str}")
            return {"status": 200, "count": count, "headers": headers, "data": data}
        elif resp.status_code == 301 or resp.status_code == 302:
            location = resp.headers.get("Location", "?")
            print(f"  [{resp.status_code}]    {label:<55} → Redirect to: {location}  {rate_str}")
            return {"status": resp.status_code, "redirect": location, "headers": headers}
        else:
            body_preview = resp.text[:200] if resp.text else ""
            print(f"  [{resp.status_code}]    {label:<55} {body_preview}  {rate_str}")
            return {"status": resp.status_code, "body": body_preview, "headers": headers}
    except requests.exceptions.ConnectionError as e:
        print(f"  [CONN]   {label:<55} → {str(e)[:120]}")
        return {"status": -1, "error": str(e)[:200]}
    except requests.exceptions.Timeout:
        print(f"  [TIMEOUT]{label:<55}")
        return {"status": -2}
    except Exception as e:
        print(f"  [ERR]    {label:<55} → {str(e)[:150]}")
        return {"status": -3, "error": str(e)[:200]}


def main():
    load_api_key()

    print("\n" + "=" * 80)
    print("TEST 1: V2 on DEFAULT SUBDOMAIN (revelator.freshdesk.com)")
    print("  Per Freshdesk Support: V2 only works on *.freshdesk.com, not vanity URLs")
    print("=" * 80)

    v2_default = "https://revelator.freshdesk.com/api/v2"
    v2_endpoints = [
        (f"{v2_default}/agents", "V2 default: /agents"),
        (f"{v2_default}/tickets", "V2 default: /tickets"),
        (f"{v2_default}/contacts", "V2 default: /contacts"),
        (f"{v2_default}/companies", "V2 default: /companies"),
        (f"{v2_default}/groups", "V2 default: /groups"),
        (f"{v2_default}/roles", "V2 default: /roles"),
        (f"{v2_default}/solutions/categories", "V2 default: /solutions/categories"),
        (f"{v2_default}/ticket_fields", "V2 default: /ticket_fields"),
        (f"{v2_default}/canned_responses", "V2 default: /canned_responses"),
    ]

    v2_results = {}
    for url, label in v2_endpoints:
        result = test_endpoint(url, label)
        v2_results[label] = result
        time.sleep(0.5)

    print("\n" + "=" * 80)
    print("TEST 2: V2 on VANITY DOMAIN (helpdesk.revelator.com) — expected to fail")
    print("=" * 80)

    v2_vanity = "https://helpdesk.revelator.com/api/v2"
    vanity_endpoints = [
        (f"{v2_vanity}/agents", "V2 vanity: /agents"),
        (f"{v2_vanity}/tickets", "V2 vanity: /tickets"),
    ]

    for url, label in vanity_endpoints:
        test_endpoint(url, label)
        time.sleep(0.5)

    print("\n" + "=" * 80)
    print("TEST 3: V1 on VANITY DOMAIN (helpdesk.revelator.com) — should still work")
    print("=" * 80)

    v1_vanity = "https://helpdesk.revelator.com"
    v1_endpoints = [
        (f"{v1_vanity}/agents.json?page=1&per_page=3", "V1 vanity: /agents.json"),
        (f"{v1_vanity}/helpdesk/tickets.json?page=1&per_page=3", "V1 vanity: /tickets.json"),
    ]

    v1_results = {}
    for url, label in v1_endpoints:
        result = test_endpoint(url, label)
        v1_results[label] = result
        time.sleep(0.5)

    print("\n" + "=" * 80)
    print("TEST 4: V1 on DEFAULT SUBDOMAIN (revelator.freshdesk.com)")
    print("=" * 80)

    v1_default_base = "https://revelator.freshdesk.com"
    v1_default_endpoints = [
        (f"{v1_default_base}/agents.json?page=1&per_page=3", "V1 default: /agents.json"),
        (f"{v1_default_base}/helpdesk/tickets.json?page=1&per_page=3", "V1 default: /tickets.json"),
    ]

    for url, label in v1_default_endpoints:
        test_endpoint(url, label)
        time.sleep(0.5)

    print("\n" + "=" * 80)
    print("RATE LIMIT SUMMARY")
    print("=" * 80)

    all_results = {**v2_results, **v1_results}
    seen_rates = set()
    for label, result in all_results.items():
        if "headers" in result:
            h = result["headers"]
            rate_key = f"{h['X-RateLimit-Total']}"
            if rate_key not in seen_rates:
                seen_rates.add(rate_key)
                print(f"  Total: {h['X-RateLimit-Total']}/min | Remaining: {h['X-RateLimit-Remaining']} | Source: {label}")

    print("\n" + "=" * 80)
    print("V2 VERDICT")
    print("=" * 80)
    v2_working = sum(1 for r in v2_results.values() if r.get("status") == 200)
    v2_total = len(v2_results)
    print(f"  V2 on default subdomain: {v2_working}/{v2_total} endpoints working")
    if v2_working > 0:
        print("  *** V2 IS AVAILABLE on revelator.freshdesk.com! ***")
        print("  Plan should be updated to use V2 as primary API.")

        first_ok = next((r for r in v2_results.values() if r.get("status") == 200), None)
        if first_ok and "data" in first_ok:
            sample = first_ok["data"]
            if isinstance(sample, list) and sample:
                print(f"\n  Sample V2 response keys: {list(sample[0].keys()) if isinstance(sample[0], dict) else 'not a dict'}")
    else:
        print("  V2 NOT available even on default subdomain.")
        print("  Continue with V1 on helpdesk.revelator.com as planned.")

    if v2_working > 0:
        print("\n" + "=" * 80)
        print("V2 DEEPER EXPLORATION — Conversations & Ticket Fields")
        print("=" * 80)

        tickets_result = v2_results.get("V2 default: /tickets")
        if tickets_result and tickets_result.get("status") == 200 and tickets_result.get("data"):
            ticket = tickets_result["data"][0]
            ticket_id = ticket.get("id")
            if ticket_id:
                test_endpoint(f"{v2_default}/tickets/{ticket_id}", f"V2: /tickets/{ticket_id} (detail)")
                time.sleep(0.5)
                test_endpoint(f"{v2_default}/tickets/{ticket_id}/conversations", f"V2: /tickets/{ticket_id}/conversations")
                time.sleep(0.5)
                test_endpoint(f"{v2_default}/tickets/{ticket_id}/time_entries", f"V2: /tickets/{ticket_id}/time_entries")
                time.sleep(0.5)
                test_endpoint(f"{v2_default}/tickets/{ticket_id}/satisfaction_ratings", f"V2: /tickets/{ticket_id}/satisfaction_ratings")
                time.sleep(0.5)


if __name__ == "__main__":
    main()
