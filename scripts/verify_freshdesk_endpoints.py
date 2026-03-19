"""
Freshdesk API Endpoint Verification Script
Tests ALL V1 and V2 endpoints, checks rate limits, counts data volumes.
Covers: agents, companies, contacts, groups, roles, tickets + Solutions (categories, folders, articles)

Usage: FRESHDESK_API_KEY=xxx python scripts/verify_freshdesk_endpoints.py
"""

import os
import sys
import json
import time
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path


DOMAIN = "helpdesk.revelator.com"
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
        print("ERROR: No FRESHDESK_API_KEY found in env or .env file")
        sys.exit(1)
    print(f"API Key: {API_KEY[:6]}...{API_KEY[-4:]}")


def api_request(url, label=""):
    auth = HTTPBasicAuth(API_KEY, "X")
    try:
        resp = requests.get(url, auth=auth, timeout=30)
        rate_total = resp.headers.get("X-RateLimit-Total", "?")
        rate_remaining = resp.headers.get("X-RateLimit-Remaining", "?")
        rate_used = resp.headers.get("X-RateLimit-Used-CurrentRequest", "?")
        rate_info = f"[Rate: {rate_remaining}/{rate_total} remaining, {rate_used} used]"

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                count = len(data)
            elif isinstance(data, dict):
                count = 1
            else:
                count = 0
            print(f"  [PASS] {label:<50} → {resp.status_code} | {count} record(s) {rate_info}")
            return {"status": resp.status_code, "data": data, "count": count,
                    "rate_total": rate_total, "rate_remaining": rate_remaining}
        elif resp.status_code == 404:
            print(f"  [404]  {label:<50} → NOT FOUND {rate_info}")
            return {"status": 404, "data": None, "count": 0,
                    "rate_total": rate_total, "rate_remaining": rate_remaining}
        elif resp.status_code == 401:
            print(f"  [401]  {label:<50} → UNAUTHORIZED {rate_info}")
            return {"status": 401, "data": None, "count": 0,
                    "rate_total": rate_total, "rate_remaining": rate_remaining}
        elif resp.status_code == 403:
            print(f"  [403]  {label:<50} → FORBIDDEN {rate_info}")
            return {"status": 403, "data": None, "count": 0,
                    "rate_total": rate_total, "rate_remaining": rate_remaining}
        elif resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "?")
            print(f"  [429]  {label:<50} → RATE LIMITED (retry after {retry_after}s) {rate_info}")
            return {"status": 429, "data": None, "count": 0,
                    "rate_total": rate_total, "rate_remaining": rate_remaining}
        else:
            print(f"  [FAIL] {label:<50} → {resp.status_code}: {resp.text[:200]} {rate_info}")
            return {"status": resp.status_code, "data": None, "count": 0,
                    "rate_total": rate_total, "rate_remaining": rate_remaining}
    except requests.exceptions.ConnectionError as e:
        print(f"  [ERR]  {label:<50} → Connection error: {str(e)[:100]}")
        return {"status": -1, "data": None, "count": 0}
    except requests.exceptions.Timeout:
        print(f"  [ERR]  {label:<50} → Timeout")
        return {"status": -2, "data": None, "count": 0}
    except Exception as e:
        print(f"  [ERR]  {label:<50} → {str(e)[:150]}")
        return {"status": -3, "data": None, "count": 0}


def paginate_count(base_url, label, per_page=100, max_pages=50):
    total = 0
    page = 1
    while page <= max_pages:
        sep = "&" if "?" in base_url else "?"
        url = f"{base_url}{sep}page={page}&per_page={per_page}"
        auth = HTTPBasicAuth(API_KEY, "X")
        try:
            resp = requests.get(url, auth=auth, timeout=30)
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data or (isinstance(data, list) and len(data) == 0):
                break
            count = len(data) if isinstance(data, list) else 1
            total += count
            if count < per_page:
                break
            page += 1
            time.sleep(0.3)
        except Exception:
            break
    return total


def test_v1_endpoints():
    print("\n" + "=" * 80)
    print("V1 ENDPOINTS (https://helpdesk.revelator.com)")
    print("=" * 80)

    base = f"https://{DOMAIN}"

    v1_endpoints = [
        ("/agents.json?page=1&per_page=5", "V1: Agents"),
        ("/companies.json?page=1&per_page=5", "V1: Companies"),
        ("/contacts.json?page=1&per_page=5", "V1: Contacts"),
        ("/groups.json", "V1: Groups"),
        ("/helpdesk/tickets.json?page=1&per_page=5", "V1: Tickets"),
        ("/solution/categories.json", "V1: Solution Categories"),
    ]

    results = {}
    for path, label in v1_endpoints:
        result = api_request(f"{base}{path}", label)
        results[label] = result
        time.sleep(0.3)

    cats = results.get("V1: Solution Categories", {})
    if cats.get("status") == 200 and cats.get("data"):
        categories = cats["data"]
        for cat in categories[:3]:
            if isinstance(cat, dict):
                cat_id = cat.get("id")
                cat_name = cat.get("name", "?")
                if cat_id:
                    r = api_request(
                        f"{base}/solution/categories/{cat_id}/folders.json",
                        f"V1: Folders in '{cat_name}' (cat {cat_id})"
                    )
                    if r.get("status") == 200 and r.get("data"):
                        folders = r["data"]
                        for folder in folders[:2]:
                            if isinstance(folder, dict):
                                folder_id = folder.get("id")
                                folder_name = folder.get("name", "?")
                                if folder_id:
                                    api_request(
                                        f"{base}/solution/folders/{folder_id}/articles.json?page=1&per_page=5",
                                        f"V1: Articles in '{folder_name}' (folder {folder_id})"
                                    )
                                    time.sleep(0.3)
                    time.sleep(0.3)

    return results


def test_v2_endpoints():
    print("\n" + "=" * 80)
    print("V2 ENDPOINTS (https://helpdesk.revelator.com/api/v2)")
    print("=" * 80)

    base = f"https://{DOMAIN}/api/v2"

    v2_endpoints = [
        ("/agents?per_page=5", "V2: Agents"),
        ("/companies?per_page=5", "V2: Companies"),
        ("/contacts?per_page=5", "V2: Contacts"),
        ("/groups?per_page=5", "V2: Groups"),
        ("/roles", "V2: Roles"),
        ("/tickets?per_page=5", "V2: Tickets"),
        ("/solutions/categories", "V2: Solution Categories"),
    ]

    results = {}
    for path, label in v2_endpoints:
        result = api_request(f"{base}{path}", label)
        results[label] = result
        time.sleep(0.3)

    cats = results.get("V2: Solution Categories", {})
    if cats.get("status") == 200 and cats.get("data"):
        categories = cats["data"]
        for cat in categories[:3]:
            if isinstance(cat, dict):
                cat_id = cat.get("id")
                cat_name = cat.get("name", "?")
                if cat_id:
                    r = api_request(
                        f"{base}/solutions/categories/{cat_id}/folders",
                        f"V2: Folders in '{cat_name}' (cat {cat_id})"
                    )
                    if r.get("status") == 200 and r.get("data"):
                        folders = r["data"]
                        for folder in folders[:2]:
                            if isinstance(folder, dict):
                                folder_id = folder.get("id")
                                folder_name = folder.get("name", "?")
                                if folder_id:
                                    api_request(
                                        f"{base}/solutions/folders/{folder_id}/articles?per_page=5",
                                        f"V2: Articles in '{folder_name}' (folder {folder_id})"
                                    )
                                    time.sleep(0.3)
                    time.sleep(0.3)

    return results


def count_all_data(api_version):
    print(f"\n" + "=" * 80)
    print(f"FULL DATA VOLUME COUNT ({api_version})")
    print("=" * 80)

    if api_version == "V2":
        base = f"https://{DOMAIN}/api/v2"
        endpoints = {
            "Agents": f"{base}/agents",
            "Companies": f"{base}/companies",
            "Contacts": f"{base}/contacts",
            "Groups": f"{base}/groups",
            "Roles": f"{base}/roles",
            "Tickets": f"{base}/tickets",
        }
    else:
        base = f"https://{DOMAIN}"
        endpoints = {
            "Agents": f"{base}/agents.json",
            "Companies": f"{base}/companies.json",
            "Contacts": f"{base}/contacts.json",
            "Groups": f"{base}/groups.json",
            "Tickets": f"{base}/helpdesk/tickets.json",
        }

    volumes = {}
    for name, url in endpoints.items():
        count = paginate_count(url, name)
        volumes[name] = count
        print(f"  {name:<30} → {count} total records")
        time.sleep(0.5)

    if api_version == "V2":
        cat_url = f"https://{DOMAIN}/api/v2/solutions/categories"
    else:
        cat_url = f"https://{DOMAIN}/solution/categories.json"

    auth = HTTPBasicAuth(API_KEY, "X")
    try:
        resp = requests.get(cat_url, auth=auth, timeout=30)
        if resp.status_code == 200:
            categories = resp.json()
            volumes["Solution Categories"] = len(categories)
            print(f"  {'Solution Categories':<30} → {len(categories)} total records")

            total_folders = 0
            total_articles = 0
            for cat in categories:
                cat_id = cat.get("id")
                if not cat_id:
                    continue

                if api_version == "V2":
                    folder_url = f"https://{DOMAIN}/api/v2/solutions/categories/{cat_id}/folders"
                else:
                    folder_url = f"https://{DOMAIN}/solution/categories/{cat_id}/folders.json"

                try:
                    fr = requests.get(folder_url, auth=auth, timeout=30)
                    if fr.status_code == 200:
                        folders = fr.json()
                        total_folders += len(folders)
                        for folder in folders:
                            folder_id = folder.get("id")
                            if not folder_id:
                                continue
                            if api_version == "V2":
                                art_url = f"https://{DOMAIN}/api/v2/solutions/folders/{folder_id}/articles"
                            else:
                                art_url = f"https://{DOMAIN}/solution/folders/{folder_id}/articles.json"
                            art_count = paginate_count(art_url, f"folder-{folder_id}")
                            total_articles += art_count
                            time.sleep(0.3)
                    time.sleep(0.3)
                except Exception:
                    pass

            volumes["Solution Folders"] = total_folders
            volumes["Solution Articles"] = total_articles
            print(f"  {'Solution Folders':<30} → {total_folders} total records")
            print(f"  {'Solution Articles':<30} → {total_articles} total records")
        else:
            print(f"  Solution Categories → HTTP {resp.status_code} (skipping folder/article count)")
    except Exception as e:
        print(f"  Solution Categories → Error: {str(e)[:100]}")

    return volumes


def sample_article(api_version):
    print(f"\n" + "=" * 80)
    print(f"SAMPLE ARTICLE CONTENT ({api_version})")
    print("=" * 80)

    auth = HTTPBasicAuth(API_KEY, "X")

    if api_version == "V2":
        cat_url = f"https://{DOMAIN}/api/v2/solutions/categories"
    else:
        cat_url = f"https://{DOMAIN}/solution/categories.json"

    try:
        resp = requests.get(cat_url, auth=auth, timeout=30)
        if resp.status_code != 200:
            print(f"  Cannot fetch categories: HTTP {resp.status_code}")
            return

        categories = resp.json()
        if not categories:
            print("  No categories found")
            return

        cat_id = categories[0].get("id")
        if api_version == "V2":
            folder_url = f"https://{DOMAIN}/api/v2/solutions/categories/{cat_id}/folders"
        else:
            folder_url = f"https://{DOMAIN}/solution/categories/{cat_id}/folders.json"

        fr = requests.get(folder_url, auth=auth, timeout=30)
        if fr.status_code != 200:
            print(f"  Cannot fetch folders: HTTP {fr.status_code}")
            return

        folders = fr.json()
        if not folders:
            print("  No folders found")
            return

        folder_id = folders[0].get("id")
        if api_version == "V2":
            art_url = f"https://{DOMAIN}/api/v2/solutions/folders/{folder_id}/articles?per_page=1"
        else:
            art_url = f"https://{DOMAIN}/solution/folders/{folder_id}/articles.json?per_page=1"

        ar = requests.get(art_url, auth=auth, timeout=30)
        if ar.status_code != 200:
            print(f"  Cannot fetch articles: HTTP {ar.status_code}")
            return

        articles = ar.json()
        if not articles:
            print("  No articles found")
            return

        article = articles[0]
        if isinstance(article, dict) and "article" in article:
            article = article["article"]

        print(f"  Title:            {article.get('title', '?')}")
        print(f"  ID:               {article.get('id', '?')}")
        print(f"  Status:           {article.get('status', '?')} (2=published)")
        print(f"  Folder ID:        {article.get('folder_id', '?')}")
        print(f"  Agent ID:         {article.get('agent_id', '?')}")
        print(f"  Tags:             {article.get('tags', [])}")
        print(f"  Created:          {article.get('created_at', '?')}")
        print(f"  Updated:          {article.get('updated_at', '?')}")
        print(f"  Hits:             {article.get('hits', '?')}")
        print(f"  Thumbs Up:        {article.get('thumbs_up', '?')}")
        print(f"  Thumbs Down:      {article.get('thumbs_down', '?')}")
        print(f"  SEO Data:         {article.get('seo_data', '?')}")

        desc = article.get("description", "")
        desc_text = article.get("description_text", "")
        print(f"  description (HTML): {len(desc) if desc else 0} chars")
        print(f"  description_text:   {len(desc_text) if desc_text else 0} chars")
        if desc:
            print(f"  HTML preview:     {desc[:300]}...")
        if desc_text:
            print(f"  Text preview:     {desc_text[:300]}...")

        print(f"\n  Full JSON keys: {list(article.keys())}")
    except Exception as e:
        print(f"  Error: {str(e)[:200]}")


def main():
    print("=" * 80)
    print("FRESHDESK API ENDPOINT VERIFICATION")
    print(f"Domain: {DOMAIN}")
    print("=" * 80)

    load_api_key()

    v1_results = test_v1_endpoints()

    v2_results = test_v2_endpoints()

    print("\n" + "=" * 80)
    print("V1 vs V2 COMPARISON")
    print("=" * 80)

    v1_working = sum(1 for v in v1_results.values() if v.get("status") == 200)
    v2_working = sum(1 for v in v2_results.values() if v.get("status") == 200)
    v1_total = len(v1_results)
    v2_total = len(v2_results)

    print(f"  V1: {v1_working}/{v1_total} endpoints working")
    print(f"  V2: {v2_working}/{v2_total} endpoints working")

    first_v2 = next((v for v in v2_results.values() if v.get("rate_total")), None)
    if first_v2:
        print(f"  Rate Limit (from V2 headers): {first_v2.get('rate_total', '?')} calls/minute")

    first_v1 = next((v for v in v1_results.values() if v.get("rate_total")), None)
    if first_v1:
        print(f"  Rate Limit (from V1 headers): {first_v1.get('rate_total', '?')} calls/minute")

    working_api = "V2" if v2_working >= v1_working else "V1"
    print(f"\n  Recommended API version: {working_api}")

    volumes = count_all_data(working_api)

    sample_article(working_api)

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"  API Version: {working_api}")
    if first_v2:
        print(f"  Rate Limit: {first_v2.get('rate_total', '?')}/minute")
    print(f"  Data Volumes:")
    for entity, count in volumes.items():
        print(f"    {entity:<30} → {count}")
    total = sum(volumes.values())
    print(f"    {'TOTAL':<30} → {total}")

    api_calls_needed = sum(
        max(1, (count // 100) + 1) for count in volumes.values()
    )
    print(f"\n  Estimated API calls for full refresh: ~{api_calls_needed}")
    if first_v2:
        rate = int(first_v2.get("rate_total", 200))
        minutes = api_calls_needed / rate if rate > 0 else 0
        print(f"  Estimated time at {rate}/min rate limit: ~{minutes:.1f} minutes")


if __name__ == "__main__":
    main()
