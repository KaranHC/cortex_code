import os
import sys
import json
import time
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path
from collections import defaultdict

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
        print("ERROR: No FRESHDESK_API_KEY found")
        sys.exit(1)

def api_get(url):
    auth = HTTPBasicAuth(API_KEY, "X")
    resp = requests.get(url, auth=auth, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    return None

def paginate(path, per_page=100):
    base = f"https://{DOMAIN}"
    all_items = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        url = f"{base}{path}{sep}page={page}&per_page={per_page}"
        data = api_get(url)
        if not data:
            break
        all_items.extend(data)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.3)
    return all_items

def unwrap(items, key):
    return [item.get(key, item) if isinstance(item, dict) and key in item else item for item in items]

def main():
    load_api_key()
    base = f"https://{DOMAIN}"

    print("=" * 90)
    print("FRESHDESK AGENT ACTIVITY ANALYSIS — Who Are the Key Contact Persons?")
    print("=" * 90)

    print("\n[1/5] Fetching agents...")
    agents_raw = paginate("/agents.json")
    agents = unwrap(agents_raw, "agent")
    agent_map = {}
    for a in agents:
        aid = a.get("id")
        user = a.get("user") or {}
        name = user.get("name") or a.get("name") or f"Agent-{aid}"
        email = user.get("email") or a.get("email") or "?"
        agent_map[aid] = {"name": name, "email": email, "active": a.get("active", True),
                          "occasional": a.get("occasional", False)}

    user_id_to_agent = {}
    for a in agents:
        uid = a.get("user_id") or (a.get("user") or {}).get("id")
        if uid:
            aid = a.get("id")
            user_id_to_agent[uid] = aid

    print(f"  Found {len(agents)} agents")
    print(f"  Agent ID → Name mapping:")
    for aid, info in sorted(agent_map.items(), key=lambda x: x[1]["name"]):
        status = "active" if info["active"] else "inactive"
        occ = " (occasional)" if info["occasional"] else ""
        print(f"    {aid}: {info['name']:<35} {info['email']:<40} [{status}{occ}]")

    print("\n[2/5] Fetching all tickets...")
    tickets_raw = paginate("/helpdesk/tickets.json")
    print(f"  Found {len(tickets_raw)} tickets")

    responder_tickets = defaultdict(list)
    requester_tickets = defaultdict(list)
    group_tickets = defaultdict(list)

    for t in tickets_raw:
        rid = t.get("responder_id")
        req_id = t.get("requester_id")
        gid = t.get("group_id")
        ticket_info = {
            "id": t.get("display_id") or t.get("id"),
            "subject": (t.get("subject") or "")[:60],
            "status": t.get("status_name") or t.get("status"),
            "priority": t.get("priority_name") or t.get("priority"),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
        }
        if rid:
            responder_tickets[rid].append(ticket_info)
        if req_id:
            requester_tickets[req_id].append(ticket_info)
        if gid:
            group_tickets[gid].append(ticket_info)

    print("\n[3/5] Fetching ticket details + conversations (notes)...")
    agent_notes = defaultdict(int)
    agent_public_notes = defaultdict(int)
    agent_private_notes = defaultdict(int)
    agent_note_tickets = defaultdict(set)
    total_notes = 0

    for i, t in enumerate(tickets_raw):
        display_id = t.get("display_id") or t.get("id")
        detail = api_get(f"{base}/helpdesk/tickets/{display_id}.json")
        if not detail:
            continue
        ht = detail.get("helpdesk_ticket", detail)
        notes = ht.get("notes", [])
        for note in notes:
            n = note.get("note", note)
            uid = n.get("user_id")
            is_private = n.get("private", False)
            is_incoming = n.get("incoming", False)
            is_deleted = n.get("deleted", False)
            if is_deleted:
                continue
            total_notes += 1
            if not is_incoming:
                agent_id = user_id_to_agent.get(uid, uid)
                agent_notes[agent_id] += 1
                agent_note_tickets[agent_id].add(display_id)
                if is_private:
                    agent_private_notes[agent_id] += 1
                else:
                    agent_public_notes[agent_id] += 1
        if (i + 1) % 10 == 0:
            print(f"  Processed {i+1}/{len(tickets_raw)} tickets...")
        time.sleep(0.3)

    print(f"  Total non-deleted notes found: {total_notes}")

    print("\n[4/5] Fetching groups...")
    groups_raw = paginate("/groups.json")
    groups = unwrap(groups_raw, "group")
    group_map = {g.get("id"): g.get("name", f"Group-{g.get('id')}") for g in groups}
    print(f"  Found {len(groups)} groups")

    print("\n[5/5] Fetching solution articles (author analysis)...")
    cats_raw = api_get(f"{base}/solution/categories.json")
    cats = unwrap(cats_raw or [], "category")
    article_authors = defaultdict(int)
    article_modifiers = defaultdict(int)
    total_articles = 0
    for cat in cats:
        folders = cat.get("folders", [])
        for f in folders:
            fid = f.get("id")
            if not fid:
                continue
            fd = api_get(f"{base}/solution/folders/{fid}.json")
            if not fd:
                continue
            folder = fd.get("folder", fd)
            articles = folder.get("articles", [])
            for art in articles:
                a = art.get("article", art) if isinstance(art, dict) else art
                total_articles += 1
                uid = a.get("user_id")
                mod_by = a.get("modified_by")
                if uid:
                    aid = user_id_to_agent.get(uid, uid)
                    article_authors[aid] += 1
                if mod_by:
                    aid = user_id_to_agent.get(mod_by, mod_by)
                    article_modifiers[aid] += 1
            time.sleep(0.3)
    print(f"  Found {total_articles} articles")

    print("\n" + "=" * 90)
    print("ANALYSIS RESULTS")
    print("=" * 90)

    def agent_name(aid):
        if aid in agent_map:
            return f"{agent_map[aid]['name']} ({agent_map[aid]['email']})"
        return f"User/Agent ID {aid}"

    print("\n── TOP TICKET RESPONDERS (assigned to resolve tickets) ──")
    sorted_responders = sorted(responder_tickets.items(), key=lambda x: len(x[1]), reverse=True)
    for rid, tix in sorted_responders[:15]:
        name = agent_name(rid)
        statuses = defaultdict(int)
        for t in tix:
            statuses[str(t["status"])] += 1
        status_str = ", ".join(f"{s}:{c}" for s, c in sorted(statuses.items(), key=lambda x: -x[1]))
        print(f"  {name:<55} → {len(tix):>3} tickets  [{status_str}]")

    print("\n── TOP CONVERSATION AUTHORS (most active in responding) ──")
    sorted_authors = sorted(agent_notes.items(), key=lambda x: x[1], reverse=True)
    for aid, count in sorted_authors[:15]:
        name = agent_name(aid)
        pub = agent_public_notes.get(aid, 0)
        priv = agent_private_notes.get(aid, 0)
        unique_tickets = len(agent_note_tickets.get(aid, set()))
        print(f"  {name:<55} → {count:>3} notes ({pub} public, {priv} private) across {unique_tickets} tickets")

    print("\n── TOP KB ARTICLE AUTHORS (created knowledge base content) ──")
    sorted_kb = sorted(article_authors.items(), key=lambda x: x[1], reverse=True)
    for aid, count in sorted_kb[:10]:
        name = agent_name(aid)
        modified = article_modifiers.get(aid, 0)
        print(f"  {name:<55} → authored {count:>3} articles, modified {modified}")

    print("\n── TOP KB ARTICLE MODIFIERS (most recent editors) ──")
    sorted_mod = sorted(article_modifiers.items(), key=lambda x: x[1], reverse=True)
    for aid, count in sorted_mod[:10]:
        name = agent_name(aid)
        authored = article_authors.get(aid, 0)
        print(f"  {name:<55} → modified {count:>3} articles (authored {authored})")

    print("\n── GROUP TICKET DISTRIBUTION ──")
    sorted_groups = sorted(group_tickets.items(), key=lambda x: len(x[1]), reverse=True)
    for gid, tix in sorted_groups:
        gname = group_map.get(gid, f"Group-{gid}")
        print(f"  {gname:<40} → {len(tix):>3} tickets")

    print("\n" + "=" * 90)
    print("RECOMMENDED CONTACT PERSONS")
    print("=" * 90)

    scores = defaultdict(lambda: {"ticket_score": 0, "note_score": 0, "kb_score": 0,
                                   "tickets": 0, "notes": 0, "articles": 0, "total": 0})

    for rid, tix in responder_tickets.items():
        if rid in agent_map:
            scores[rid]["ticket_score"] = len(tix) * 2
            scores[rid]["tickets"] = len(tix)

    for aid, count in agent_notes.items():
        if aid in agent_map:
            scores[aid]["note_score"] = count * 3
            scores[aid]["notes"] = count

    for aid, count in article_authors.items():
        if aid in agent_map:
            scores[aid]["kb_score"] = count * 5
            scores[aid]["articles"] = count

    for aid in scores:
        s = scores[aid]
        s["total"] = s["ticket_score"] + s["note_score"] + s["kb_score"]

    ranked = sorted(scores.items(), key=lambda x: x[1]["total"], reverse=True)

    print("\nComposite Score = (tickets × 2) + (conversation notes × 3) + (KB articles × 5)")
    print(f"{'Rank':<5} {'Agent':<50} {'Tickets':>8} {'Notes':>8} {'Articles':>9} {'Score':>8}")
    print("-" * 90)
    for i, (aid, s) in enumerate(ranked[:15], 1):
        name = agent_map[aid]["name"]
        email = agent_map[aid]["email"]
        active = "●" if agent_map[aid]["active"] else "○"
        print(f"  {active} {i:<3} {name:<35} {email:<30} {s['tickets']:>5} {s['notes']:>8} {s['articles']:>9} {s['total']:>8}")

    print("\n● = active agent  ○ = inactive/deleted agent")
    print("\nTop 3 recommended contacts:")
    for i, (aid, s) in enumerate(ranked[:3], 1):
        info = agent_map[aid]
        print(f"\n  {i}. {info['name']}")
        print(f"     Email: {info['email']}")
        print(f"     Tickets assigned: {s['tickets']}")
        print(f"     Conversation notes: {s['notes']} ({agent_public_notes.get(aid,0)} public, {agent_private_notes.get(aid,0)} private)")
        print(f"     KB articles authored: {s['articles']}")
        print(f"     Composite score: {s['total']}")

    results = {
        "agents": agent_map,
        "responder_tickets": {str(k): len(v) for k, v in responder_tickets.items()},
        "agent_notes": {str(k): v for k, v in agent_notes.items()},
        "article_authors": {str(k): v for k, v in article_authors.items()},
        "article_modifiers": {str(k): v for k, v in article_modifiers.items()},
        "group_distribution": {str(k): len(v) for k, v in group_tickets.items()},
        "rankings": [{"agent_id": aid, "name": agent_map[aid]["name"],
                       "email": agent_map[aid]["email"], **s}
                      for aid, s in ranked[:15] if aid in agent_map]
    }
    out_path = Path(__file__).parent / "freshdesk_agent_analysis.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nFull results saved to: {out_path}")

if __name__ == "__main__":
    main()
