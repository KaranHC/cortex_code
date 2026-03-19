"""
RevSearch API Key Verification Script
Validates Freshdesk and GitBook API keys have correct permissions.
Usage: python scripts/verify_api_keys.py
Reads credentials from .env file in project root.
"""

import os
import sys
import requests
from pathlib import Path

def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print(f"ERROR: .env file not found at {env_path}")
        sys.exit(1)
    env = {}
    for line in env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip()
    return env


def verify_freshdesk(api_key, domain="helpdesk.revelator.com"):
    print("\n" + "=" * 60)
    print("FRESHDESK API VERIFICATION (V1 API)")
    print(f"Domain: {domain}")
    print("=" * 60)

    base_url = f"https://{domain}"
    auth = (api_key, "X")
    headers = {"Content-Type": "application/json"}

    endpoints = [
        ("Tickets", "/helpdesk/tickets.json?page=1&per_page=1"),
        ("Contacts", "/contacts.json?page=1&per_page=1"),
        ("Companies", "/companies.json?page=1&per_page=1"),
        ("Agents", "/agents.json?page=1&per_page=1"),
        ("Groups", "/groups.json"),
        ("Solutions (KB)", "/solution/categories.json"),
    ]

    all_pass = True
    for name, path in endpoints:
        try:
            resp = requests.get(f"{base_url}{path}", auth=auth, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                count = len(data) if isinstance(data, list) else 1
                print(f"  [PASS] {name:<30} -> {count} record(s)")
            elif resp.status_code == 401:
                print(f"  [FAIL] {name:<30} -> 401 Unauthorized (invalid API key)")
                all_pass = False
            elif resp.status_code == 403:
                print(f"  [FAIL] {name:<30} -> 403 Forbidden (insufficient permissions)")
                all_pass = False
            elif resp.status_code == 404:
                print(f"  [WARN] {name:<30} -> 404 Not Found")
            else:
                print(f"  [FAIL] {name:<30} -> HTTP {resp.status_code}: {resp.text[:100]}")
                all_pass = False
        except requests.exceptions.ConnectionError:
            print(f"  [FAIL] {name:<30} -> Connection error (check domain: {domain})")
            all_pass = False
        except requests.exceptions.Timeout:
            print(f"  [FAIL] {name:<30} -> Request timed out")
            all_pass = False
        except Exception as e:
            print(f"  [FAIL] {name:<30} -> {str(e)[:100]}")
            all_pass = False

    return all_pass


def verify_gitbook(api_token):
    print("\n" + "=" * 60)
    print("GITBOOK API VERIFICATION")
    print("=" * 60)

    base_url = "https://api.gitbook.com/v1"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    all_pass = True

    try:
        resp = requests.get(f"{base_url}/user", headers=headers, timeout=15)
        if resp.status_code == 200:
            user = resp.json()
            print(f"  [PASS] Authentication            → Logged in as: {user.get('displayName', user.get('id', '?'))}")
        elif resp.status_code == 401:
            print(f"  [FAIL] Authentication            → 401 Unauthorized (invalid token)")
            return False
        else:
            print(f"  [FAIL] Authentication            → HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"  [FAIL] Authentication            → {str(e)[:100]}")
        return False

    endpoints = [
        ("Organizations", "orgs"),
    ]

    for name, endpoint in endpoints:
        try:
            resp = requests.get(f"{base_url}/{endpoint}", headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", data) if isinstance(data, dict) else data
                count = len(items) if isinstance(items, list) else 1
                print(f"  [PASS] {name:<30} → {count} record(s)")
            elif resp.status_code == 403:
                print(f"  [FAIL] {name:<30} → 403 Forbidden (token lacks scope)")
                all_pass = False
            else:
                print(f"  [WARN] {name:<30} → HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [FAIL] {name:<30} → {str(e)[:100]}")
            all_pass = False

    orgs_resp = requests.get(f"{base_url}/orgs", headers=headers, timeout=15)
    if orgs_resp.status_code != 200:
        print(f"  [FAIL] Cannot list orgs → HTTP {orgs_resp.status_code}")
        return False

    orgs = orgs_resp.json().get("items", [])
    total_spaces = 0
    first_space = None
    for org in orgs:
        org_id = org["id"]
        org_title = org.get("title", org_id)
        try:
            resp = requests.get(f"{base_url}/orgs/{org_id}/spaces", headers=headers, timeout=15)
            if resp.status_code == 200:
                spaces = resp.json().get("items", [])
                total_spaces += len(spaces)
                if not first_space and spaces:
                    first_space = spaces[0]
                print(f"  [PASS] Spaces (org: {org_title:<15}) → {len(spaces)} space(s)")
            else:
                print(f"  [WARN] Spaces (org: {org_title:<15}) → HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [FAIL] Spaces (org: {org_title:<15}) → {str(e)[:100]}")
            all_pass = False

    print(f"  [INFO] Total spaces across all orgs: {total_spaces}")

    if first_space:
        space_id = first_space["id"]
        space_title = first_space.get("title", space_id)

        for name, endpoint in [
            ("Pages (list)", f"spaces/{space_id}/content"),
            ("Collections", f"spaces/{space_id}/collections"),
        ]:
            try:
                r = requests.get(f"{base_url}/{endpoint}", headers=headers, timeout=15)
                if r.status_code == 200:
                    d = r.json()
                    items = d.get("pages", d.get("items", []))
                    print(f"  [PASS] {name:<30} → {len(items)} record(s) (space: {space_title})")
                else:
                    print(f"  [WARN] {name:<30} → HTTP {r.status_code} (space: {space_title})")
            except Exception as e:
                print(f"  [FAIL] {name:<30} → {str(e)[:100]}")
                all_pass = False

        try:
            pages_resp = requests.get(f"{base_url}/spaces/{space_id}/content", headers=headers, timeout=15)
            pages = pages_resp.json().get("pages", [])
            if pages:
                page_id = pages[0].get("id")
                r = requests.get(f"{base_url}/spaces/{space_id}/content/page/{page_id}", headers=headers, timeout=15)
                if r.status_code == 200:
                    md = r.json().get("markdown", "")
                    print(f"  [PASS] Page content (markdown)       -> {len(md)} chars (page: {pages[0].get('title', page_id)})")
                else:
                    print(f"  [WARN] Page content (markdown)       -> HTTP {r.status_code}")
        except Exception as e:
            print(f"  [FAIL] Page content              -> {str(e)[:100]}")
            all_pass = False
    else:
        print(f"  [WARN] No spaces found — cannot test page/collection access")

    return all_pass


def main():
    print("RevSearch API Key Verification")
    print("Checking .env credentials...\n")

    env = load_env()

    freshdesk_key = env.get("FRESHDESK_API")
    gitbook_key = env.get("GITBOOK_API")

    results = {}

    if freshdesk_key:
        results["Freshdesk"] = verify_freshdesk(freshdesk_key)
    else:
        print("\n  [SKIP] Freshdesk: No FRESHDESK_API key found in .env")
        results["Freshdesk"] = None

    if gitbook_key:
        results["GitBook"] = verify_gitbook(gitbook_key)
    else:
        print("\n  [SKIP] GitBook: No GITBOOK_API key found in .env")
        results["GitBook"] = None

    notion_key = env.get("NOTION_API")
    if notion_key:
        print("\n  [INFO] Notion: API key found but verification not yet implemented")
        results["Notion"] = None
    else:
        print("\n  [SKIP] Notion: No NOTION_API key found in .env")
        results["Notion"] = None

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for service, passed in results.items():
        if passed is True:
            print(f"  {service}: ALL CHECKS PASSED")
        elif passed is False:
            print(f"  {service}: SOME CHECKS FAILED")
        else:
            print(f"  {service}: SKIPPED")

    if any(v is False for v in results.values()):
        print("\nFix the failing checks before running ingestion.")
        sys.exit(1)
    else:
        print("\nAll available API keys are valid and have the required permissions.")


if __name__ == "__main__":
    main()
