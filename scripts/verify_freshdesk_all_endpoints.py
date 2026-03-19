"""
Freshdesk V1 API — COMPREHENSIVE Endpoint Verification
Tests ALL known V1 GET endpoints beyond the basic 7 entities.
Covers: discussions, time_sheets, ticket_fields, contact_fields, company_fields,
        surveys, ticket conversations, agent filters, contact filters, canned responses,
        products, business_hours, SLA policies, email_configs, scenario_automations, etc.

Usage: python scripts/verify_freshdesk_all_endpoints.py
"""

import os
import sys
import json
import time
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path

DOMAIN = "helpdesk.revelator.com"
BASE = f"https://{DOMAIN}"
API_KEY = None
RESULTS = []

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

def get_auth():
    return HTTPBasicAuth(API_KEY, "X")

def test_endpoint(url, label, category=""):
    try:
        resp = requests.get(url, auth=get_auth(), timeout=30)
        status = resp.status_code
        rate_total = resp.headers.get("X-RateLimit-Total", "?")
        rate_remaining = resp.headers.get("X-RateLimit-Remaining", "?")

        data = None
        count = 0
        keys = []
        wrapping = "N/A"
        sample = ""

        if status == 200:
            try:
                data = resp.json()
            except Exception:
                data = resp.text[:200]

            if isinstance(data, list):
                count = len(data)
                wrapping = "flat_list"
                if count > 0 and isinstance(data[0], dict):
                    first = data[0]
                    inner_keys = list(first.keys())
                    if len(inner_keys) == 1 and isinstance(first[inner_keys[0]], dict):
                        wrapping = f"wrapped:{inner_keys[0]}"
                        keys = list(first[inner_keys[0]].keys())[:10]
                        sample = json.dumps({k: str(first[inner_keys[0]].get(k, ""))[:80] for k in keys[:5]}, indent=2)
                    else:
                        keys = inner_keys[:10]
                        sample = json.dumps({k: str(first.get(k, ""))[:80] for k in keys[:5]}, indent=2)
                elif count > 0:
                    sample = str(data[0])[:200]
            elif isinstance(data, dict):
                count = 1
                top_keys = list(data.keys())
                if len(top_keys) == 1 and isinstance(data[top_keys[0]], (dict, list)):
                    wrapping = f"wrapped:{top_keys[0]}"
                    inner = data[top_keys[0]]
                    if isinstance(inner, dict):
                        keys = list(inner.keys())[:10]
                        sample = json.dumps({k: str(inner.get(k, ""))[:80] for k in keys[:5]}, indent=2)
                    elif isinstance(inner, list):
                        count = len(inner)
                        if count > 0 and isinstance(inner[0], dict):
                            keys = list(inner[0].keys())[:10]
                            sample = json.dumps({k: str(inner[0].get(k, ""))[:80] for k in keys[:5]}, indent=2)
                else:
                    keys = top_keys[:10]
                    sample = json.dumps({k: str(data.get(k, ""))[:80] for k in keys[:5]}, indent=2)

            status_str = "PASS"
        elif status == 404:
            status_str = "404"
        elif status == 401:
            status_str = "401"
        elif status == 403:
            status_str = "403"
        elif status == 302:
            location = resp.headers.get("Location", "?")
            status_str = f"302→{location[:60]}"
        else:
            status_str = f"HTTP_{status}"

        result = {
            "category": category,
            "label": label,
            "url": url,
            "status": status,
            "status_str": status_str,
            "count": count,
            "keys": keys,
            "wrapping": wrapping,
            "sample": sample,
            "rate_total": rate_total,
            "rate_remaining": rate_remaining,
        }
        RESULTS.append(result)

        if status == 200:
            print(f"  [PASS] {label:<55} → {status} | {count:>4} records | wrap={wrapping} | keys={keys[:6]}")
        else:
            print(f"  [{status:>3}]  {label:<55} → {status_str}")

        return result

    except requests.exceptions.ConnectionError as e:
        print(f"  [ERR]  {label:<55} → Connection error: {str(e)[:80]}")
        RESULTS.append({"category": category, "label": label, "url": url, "status": -1, "status_str": "CONN_ERR", "count": 0, "keys": [], "wrapping": "N/A", "sample": ""})
        return None
    except Exception as e:
        print(f"  [ERR]  {label:<55} → {str(e)[:100]}")
        RESULTS.append({"category": category, "label": label, "url": url, "status": -2, "status_str": "ERROR", "count": 0, "keys": [], "wrapping": "N/A", "sample": ""})
        return None


def section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def main():
    print("=" * 80)
    print("FRESHDESK V1 API — COMPREHENSIVE ENDPOINT VERIFICATION")
    print(f"Domain: {DOMAIN}")
    print("=" * 80)

    load_api_key()

    ticket_id = None
    first_cat_id = None

    section("1. EXISTING KNOWN-WORKING ENDPOINTS (baseline)")
    r = test_endpoint(f"{BASE}/agents.json?page=1&per_page=5", "Agents (baseline)", "Agents")
    time.sleep(0.3)
    r = test_endpoint(f"{BASE}/companies.json?page=1&per_page=5", "Companies (baseline)", "Companies")
    time.sleep(0.3)
    r = test_endpoint(f"{BASE}/contacts.json?page=1&per_page=5", "Contacts (baseline)", "Contacts")
    time.sleep(0.3)
    r = test_endpoint(f"{BASE}/groups.json", "Groups (baseline)", "Groups")
    time.sleep(0.3)
    r = test_endpoint(f"{BASE}/helpdesk/tickets.json?page=1&per_page=5", "Tickets (baseline)", "Tickets")
    if r and r["status"] == 200 and r.get("count", 0) > 0:
        try:
            data = requests.get(f"{BASE}/helpdesk/tickets.json?page=1&per_page=1", auth=get_auth(), timeout=30).json()
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                ticket_id = first.get("display_id") or first.get("id")
                if isinstance(first, dict) and "helpdesk_ticket" in first:
                    ticket_id = first["helpdesk_ticket"].get("display_id") or first["helpdesk_ticket"].get("id")
                print(f"  → Got ticket_id for sub-tests: {ticket_id}")
        except Exception as e:
            print(f"  → Could not extract ticket_id: {e}")
    time.sleep(0.3)
    r = test_endpoint(f"{BASE}/solution/categories.json", "Solution Categories (baseline)", "Solutions")
    if r and r["status"] == 200:
        try:
            data = requests.get(f"{BASE}/solution/categories.json", auth=get_auth(), timeout=30).json()
            if isinstance(data, list) and len(data) > 0:
                cat = data[0]
                if isinstance(cat, dict):
                    first_cat_id = cat.get("id")
                    if "category" in cat and isinstance(cat["category"], dict):
                        first_cat_id = cat["category"].get("id")
                    print(f"  → Got first category_id: {first_cat_id}")
        except Exception:
            pass
    time.sleep(0.3)

    section("2. TICKET FILTERS & VIEWS")
    test_endpoint(f"{BASE}/helpdesk/tickets/filter/all_tickets?format=json", "Ticket filter: all_tickets", "Ticket Filters")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/tickets/filter/new_and_my_open?format=json", "Ticket filter: new_and_my_open", "Ticket Filters")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/tickets/filter/spam?format=json", "Ticket filter: spam", "Ticket Filters")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/tickets/filter/deleted?format=json", "Ticket filter: deleted", "Ticket Filters")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/tickets/filter/monitored_by?format=json", "Ticket filter: monitored_by", "Ticket Filters")
    time.sleep(0.3)

    section("3. SINGLE TICKET DETAIL + CONVERSATIONS")
    if ticket_id:
        test_endpoint(f"{BASE}/helpdesk/tickets/{ticket_id}.json", f"Single ticket detail (id={ticket_id})", "Ticket Detail")
        time.sleep(0.3)
        test_endpoint(f"{BASE}/helpdesk/tickets/{ticket_id}/conversations.json", f"Ticket conversations (id={ticket_id})", "Ticket Conversations")
        time.sleep(0.3)
        test_endpoint(f"{BASE}/helpdesk/tickets/{ticket_id}/conversations/note.json", f"Ticket notes (id={ticket_id})", "Ticket Conversations")
        time.sleep(0.3)

    section("4. TICKET FIELD METADATA")
    test_endpoint(f"{BASE}/ticket_fields.json", "Ticket fields metadata", "Field Metadata")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/ticket_fields.json", "Ticket fields (alt path)", "Field Metadata")
    time.sleep(0.3)

    section("5. CONTACT FIELD METADATA")
    test_endpoint(f"{BASE}/admin/contact_fields.json", "Contact fields metadata", "Field Metadata")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/contact_fields.json", "Contact fields (alt path)", "Field Metadata")
    time.sleep(0.3)

    section("6. COMPANY FIELD METADATA")
    test_endpoint(f"{BASE}/admin/company_fields.json", "Company fields metadata", "Field Metadata")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/company_fields.json", "Company fields (alt path)", "Field Metadata")
    time.sleep(0.3)

    section("7. TIME ENTRIES / TIME SHEETS")
    test_endpoint(f"{BASE}/helpdesk/time_sheets.json", "Global time entries", "Time Entries")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/time_sheets.json", "Time entries (alt path)", "Time Entries")
    time.sleep(0.3)
    if ticket_id:
        test_endpoint(f"{BASE}/helpdesk/tickets/{ticket_id}/time_sheets.json", f"Time entries on ticket {ticket_id}", "Time Entries")
        time.sleep(0.3)

    section("8. FORUMS / DISCUSSIONS")
    test_endpoint(f"{BASE}/discussions/categories.json", "Discussion categories", "Discussions")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/discussions.json", "Discussions (root)", "Discussions")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/categories.json", "Categories (alt root)", "Discussions")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/discussions/forums.json", "Discussion forums (all)", "Discussions")
    time.sleep(0.3)

    disc_cat_result = None
    for r in RESULTS:
        if "Discussion categories" in r.get("label", "") and r.get("status") == 200:
            disc_cat_result = r
            break

    if disc_cat_result and disc_cat_result.get("count", 0) > 0:
        try:
            resp = requests.get(f"{BASE}/discussions/categories.json", auth=get_auth(), timeout=30)
            disc_cats = resp.json()
            if isinstance(disc_cats, list) and len(disc_cats) > 0:
                dc = disc_cats[0]
                dc_id = dc.get("id")
                if isinstance(dc, dict) and len(dc) == 1:
                    key = list(dc.keys())[0]
                    dc_id = dc[key].get("id", dc_id)
                if dc_id:
                    test_endpoint(f"{BASE}/discussions/categories/{dc_id}.json", f"Discussion category detail (id={dc_id})", "Discussions")
                    time.sleep(0.3)
                    test_endpoint(f"{BASE}/discussions/categories/{dc_id}/forums.json", f"Forums in disc category {dc_id}", "Discussions")
                    time.sleep(0.3)
        except Exception as e:
            print(f"  → Error exploring discussion categories: {e}")

    test_endpoint(f"{BASE}/discussions/topics.json", "Discussion topics (all)", "Discussions")
    time.sleep(0.3)

    section("9. SATISFACTION RATINGS / CSAT SURVEYS")
    test_endpoint(f"{BASE}/surveys/satisfaction_ratings.json", "Satisfaction ratings", "CSAT")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/surveys.json", "Surveys (root)", "CSAT")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/surveys.json", "Surveys (helpdesk path)", "CSAT")
    time.sleep(0.3)
    if ticket_id:
        test_endpoint(f"{BASE}/helpdesk/tickets/{ticket_id}/surveys.json", f"Ticket surveys (id={ticket_id})", "CSAT")
        time.sleep(0.3)

    section("10. AGENT EXTRAS")
    test_endpoint(f"{BASE}/agents/filter/active.json", "Agents filter: active", "Agent Extras")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/agents/filter/deleted.json", "Agents filter: deleted", "Agent Extras")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/agents/filter/occasional.json", "Agents filter: occasional", "Agent Extras")
    time.sleep(0.3)

    section("11. CONTACT FILTERS")
    test_endpoint(f"{BASE}/contacts.json?state=verified", "Contacts: state=verified", "Contact Filters")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/contacts.json?state=all", "Contacts: state=all", "Contact Filters")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/contacts.json?state=deleted", "Contacts: state=deleted", "Contact Filters")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/contacts.json?state=unverified", "Contacts: state=unverified", "Contact Filters")
    time.sleep(0.3)

    section("12. SOLUTION EXTRAS")
    if first_cat_id:
        test_endpoint(f"{BASE}/solution/categories/{first_cat_id}.json", f"Solution category detail (id={first_cat_id})", "Solution Extras")
        time.sleep(0.3)
        test_endpoint(f"{BASE}/solution/categories/{first_cat_id}/folders.json", f"Solution folders in cat {first_cat_id}", "Solution Extras")
        time.sleep(0.3)
    test_endpoint(f"{BASE}/solutions/categories.json", "Solutions (alt path /solutions/)", "Solution Extras")
    time.sleep(0.3)

    section("13. ROLES (EXPECTED 404)")
    test_endpoint(f"{BASE}/roles.json", "Roles (root)", "Roles")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/admin/roles.json", "Roles (admin path)", "Roles")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/roles.json", "Roles (helpdesk path)", "Roles")
    time.sleep(0.3)

    section("14. CANNED RESPONSES")
    test_endpoint(f"{BASE}/admin/canned_responses/folders.json", "Canned response folders", "Canned Responses")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/canned_responses.json", "Canned responses (root)", "Canned Responses")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/helpdesk/canned_responses.json", "Canned responses (helpdesk)", "Canned Responses")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/admin/canned_responses.json", "Canned responses (admin)", "Canned Responses")
    time.sleep(0.3)

    section("15. PRODUCTS")
    test_endpoint(f"{BASE}/products.json", "Products", "Products")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/admin/products.json", "Products (admin)", "Products")
    time.sleep(0.3)

    section("16. BUSINESS HOURS & SLA")
    test_endpoint(f"{BASE}/business_hours.json", "Business hours", "Config")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/admin/business_hours.json", "Business hours (admin)", "Config")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/sla_policies.json", "SLA policies", "Config")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/admin/sla_policies.json", "SLA policies (admin)", "Config")
    time.sleep(0.3)

    section("17. EMAIL CONFIGS")
    test_endpoint(f"{BASE}/email_configs.json", "Email configs", "Config")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/admin/email_configs.json", "Email configs (admin)", "Config")
    time.sleep(0.3)

    section("18. SCENARIO AUTOMATIONS")
    test_endpoint(f"{BASE}/scenario_automations.json", "Scenario automations", "Automations")
    time.sleep(0.3)
    test_endpoint(f"{BASE}/admin/automations.json", "Automations (admin)", "Automations")
    time.sleep(0.3)

    section("19. V2 QUICK CHECK (for new entities)")
    v2 = f"{BASE}/api/v2"
    test_endpoint(f"{v2}/canned_response_folders", "V2: Canned response folders", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/products", "V2: Products", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/business_hours", "V2: Business hours", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/sla_policies", "V2: SLA policies", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/email_configs", "V2: Email configs", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/surveys/satisfaction_ratings", "V2: Satisfaction ratings", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/time_entries", "V2: Time entries", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/ticket_fields", "V2: Ticket fields", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/contact_fields", "V2: Contact fields", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/company_fields", "V2: Company fields", "V2 Check")
    time.sleep(0.3)
    test_endpoint(f"{v2}/account", "V2: Account info", "V2 Check")
    time.sleep(0.3)

    print("\n\n")
    print("=" * 120)
    print("COMPREHENSIVE RESULTS SUMMARY")
    print("=" * 120)
    print(f"{'Status':<8} {'Category':<20} {'Label':<55} {'Count':>6} {'Wrapping':<25} {'Keys (first 6)'}")
    print("-" * 120)

    working = []
    not_found = []
    other = []

    for r in RESULTS:
        status = r.get("status", -1)
        line = f"{r.get('status_str','?'):<8} {r.get('category',''):<20} {r.get('label',''):<55} {r.get('count',0):>6} {r.get('wrapping',''):<25} {r.get('keys',[])[:6]}"
        if status == 200:
            working.append(line)
        elif status == 404:
            not_found.append(line)
        else:
            other.append(line)

    print("\n--- WORKING (200) ---")
    for l in working:
        print(f"  {l}")

    print(f"\n--- NOT FOUND (404) --- [{len(not_found)} endpoints]")
    for l in not_found:
        print(f"  {l}")

    print(f"\n--- OTHER STATUS --- [{len(other)} endpoints]")
    for l in other:
        print(f"  {l}")

    print(f"\n{'='*80}")
    print(f"TOTALS: {len(working)} working | {len(not_found)} not found | {len(other)} other errors")
    print(f"{'='*80}")

    print("\n\n--- WORKING ENDPOINTS WITH SAMPLE DATA ---")
    for r in RESULTS:
        if r.get("status") == 200 and r.get("sample"):
            print(f"\n  {r['label']} ({r['url']})")
            print(f"  Keys: {r.get('keys', [])}")
            print(f"  Wrapping: {r.get('wrapping', 'N/A')}")
            print(f"  Count: {r.get('count', 0)}")
            print(f"  Sample:\n{r.get('sample', '')}")

    output_path = Path(__file__).parent / "freshdesk_all_endpoints_results.json"
    with open(output_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print(f"\n\nFull results saved to: {output_path}")


if __name__ == "__main__":
    main()
