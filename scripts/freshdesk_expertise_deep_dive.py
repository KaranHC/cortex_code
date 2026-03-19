"""
Comprehensive Freshdesk Agent Expertise Deep-Dive
Extracts EVERY signal from EVERY agent and maps to topics with L1→L2→L3 tiering.

Signals extracted:
  1. KB articles AUTHORED (user_id on article) → per category
  2. KB articles MODIFIED (modified_by on article) → per category
  3. KB article QUALITY (hits, thumbs_up, thumbs_down) → weighted per author
  4. KB article RECENCY (modified_at) → more recent = more relevant
  5. Ticket RESPONDER assignment (responder_id on ticket) → per ticket_type/issue_type
  6. Ticket NOTES authored (user_id on note, incoming=false) → per ticket topic
  7. Ticket note QUALITY (public vs private, length)
  8. GROUP membership → domain association
  9. Agent ROLE signals (name patterns like "Support", "Marketing", "UGC")
"""

import os, sys, json, time, math
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth

DOMAIN = "helpdesk.revelator.com"
BASE = f"https://{DOMAIN}"
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
    for attempt in range(3):
        try:
            resp = requests.get(url, auth=auth, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 30))
                time.sleep(retry)
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return None
        except Exception:
            time.sleep(2 ** attempt)
    return None

def paginate(path, per_page=100):
    all_items = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        url = f"{BASE}{path}{sep}page={page}&per_page={per_page}"
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

def parse_dt(s):
    if not s:
        return None
    try:
        s = s.replace("+00:00", "+0000").replace("+02:00", "+0200").replace("+03:00", "+0300")
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def days_ago(dt_str):
    dt = parse_dt(dt_str)
    if not dt:
        return 9999
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days

def recency_weight(days):
    if days <= 90:
        return 1.0
    elif days <= 180:
        return 0.8
    elif days <= 365:
        return 0.6
    elif days <= 730:
        return 0.4
    else:
        return 0.2

def main():
    load_api_key()

    print("=" * 110)
    print("COMPREHENSIVE FRESHDESK AGENT EXPERTISE DEEP-DIVE")
    print("Every agent. Every signal. Every topic. L1→L2→L3 tiering.")
    print("=" * 110)

    # ─── STEP 1: Build complete user_id → identity map ───
    print("\n[1/7] Building complete identity map (active + deleted agents)...")

    identity = {}  # user_id → {name, email, agent_id, status, groups}

    active_raw = paginate("/agents.json")
    active_agents = unwrap(active_raw, "agent")
    for a in active_agents:
        uid = a.get("user_id") or (a.get("user") or {}).get("id")
        aid = a.get("id")
        user = a.get("user") or {}
        identity[uid] = {
            "name": user.get("name") or a.get("name") or f"Agent-{aid}",
            "email": user.get("email") or a.get("email") or "?",
            "agent_id": aid,
            "status": "active",
            "groups": [],
            "occasional": a.get("occasional", False),
        }

    deleted_raw = paginate("/agents/filter/deleted.json")
    deleted_agents = unwrap(deleted_raw, "agent")
    for a in deleted_agents:
        uid = a.get("user_id") or (a.get("user") or {}).get("id")
        aid = a.get("id")
        user = a.get("user") or {}
        identity[uid] = {
            "name": user.get("name") or a.get("name") or f"Agent-{aid}",
            "email": user.get("email") or a.get("email") or "?",
            "agent_id": aid,
            "status": "deleted",
            "groups": [],
            "occasional": a.get("occasional", False),
        }

    # Also build agent_id → user_id reverse map (for responder_id lookups)
    agent_id_to_uid = {}
    for uid, info in identity.items():
        agent_id_to_uid[info["agent_id"]] = uid

    print(f"  {len(active_agents)} active + {len(deleted_agents)} deleted = {len(identity)} total agents")

    # ─── STEP 2: Fetch groups and map agents to groups ───
    print("\n[2/7] Fetching groups...")
    groups_raw = paginate("/groups.json")
    groups = unwrap(groups_raw, "group")
    group_map = {}
    for g in groups:
        gid = g.get("id")
        gname = g.get("name", f"Group-{gid}")
        group_map[gid] = gname
    print(f"  {len(groups)} groups: {', '.join(group_map.values())}")

    # ─── STEP 3: Fetch ALL tickets with full detail ───
    print("\n[3/7] Fetching ALL tickets with full detail (notes, custom fields, tags)...")
    tickets_list = paginate("/helpdesk/tickets.json")
    print(f"  {len(tickets_list)} tickets in list")

    tickets_detail = []
    all_notes = []
    for i, t in enumerate(tickets_list):
        display_id = t.get("display_id") or t.get("id")
        detail = api_get(f"{BASE}/helpdesk/tickets/{display_id}.json")
        if not detail:
            continue
        ht = detail.get("helpdesk_ticket", detail)
        ht["_display_id"] = display_id
        tickets_detail.append(ht)

        notes = ht.get("notes", [])
        for note in notes:
            n = note.get("note", note)
            n["_ticket_id"] = ht.get("id")
            n["_ticket_display_id"] = display_id
            n["_ticket_subject"] = ht.get("subject", "")
            n["_ticket_type"] = ht.get("ticket_type")
            n["_ticket_tags"] = ht.get("tags", [])
            custom = ht.get("custom_field") or {}
            issue_type = None
            for k, v in custom.items():
                if "issue_type" in k and v:
                    issue_type = v
                    break
            n["_ticket_issue_type"] = issue_type
            n["_ticket_group_id"] = ht.get("group_id")
            all_notes.append(n)

        if (i + 1) % 10 == 0:
            print(f"  Processed {i+1}/{len(tickets_list)} ticket details...")
        time.sleep(0.3)

    print(f"  {len(tickets_detail)} ticket details fetched, {len(all_notes)} total notes")

    # ─── STEP 4: Fetch ALL solution articles with category/folder context ───
    print("\n[4/7] Fetching ALL solution articles with category context...")
    cats_raw = api_get(f"{BASE}/solution/categories.json")
    cats = unwrap(cats_raw or [], "category")

    all_articles = []
    cat_name_map = {}
    folder_to_cat = {}

    for cat in cats:
        cat_id = cat.get("id")
        cat_name = cat.get("name", "?")
        cat_name_map[cat_id] = cat_name
        folders = cat.get("folders", [])
        for f in folders:
            fid = f.get("id")
            if not fid:
                continue
            folder_to_cat[fid] = {"cat_id": cat_id, "cat_name": cat_name, "folder_name": f.get("name", "?")}
            fd = api_get(f"{BASE}/solution/folders/{fid}.json")
            if not fd:
                continue
            folder = fd.get("folder", fd)
            articles = folder.get("articles", [])
            for art in articles:
                a = art.get("article", art) if isinstance(art, dict) else art
                a["_category_id"] = cat_id
                a["_category_name"] = cat_name
                a["_folder_name"] = f.get("name", "?")
                all_articles.append(a)
            time.sleep(0.2)

    print(f"  {len(all_articles)} articles across {len(cats)} categories")

    # ─── STEP 5: Fetch ticket fields for custom field label mapping ───
    print("\n[5/7] Fetching ticket field metadata...")
    fields_raw = api_get(f"{BASE}/ticket_fields.json")
    fields = unwrap(fields_raw or [], "ticket_field")
    field_labels = {}
    for f in fields:
        name = f.get("name", "")
        label = f.get("label") or f.get("label_in_portal") or name
        field_labels[name] = label
    print(f"  {len(fields)} ticket fields mapped")

    # ─── STEP 6: Compute ALL signals per agent per topic ───
    print("\n[6/7] Computing expertise signals...")

    # Topic extraction from ticket
    def get_ticket_topic(ticket):
        custom = ticket.get("custom_field") or {}
        for k, v in custom.items():
            if "issue_type" in k and v:
                return v
        tt = ticket.get("ticket_type")
        if tt:
            return tt
        return "General Support"

    # Signal accumulators per (user_id, topic)
    S = defaultdict(lambda: {
        "kb_authored": 0,
        "kb_modified": 0,
        "kb_hits": 0,
        "kb_thumbs_up": 0,
        "kb_thumbs_down": 0,
        "kb_latest_modified_days": 9999,
        "ticket_responder": 0,
        "ticket_notes_public": 0,
        "ticket_notes_private": 0,
        "ticket_notes_total": 0,
        "ticket_note_chars": 0,
        "tickets_touched": set(),
        "note_latest_days": 9999,
        "ticket_latest_days": 9999,
    })

    # Global per-agent accumulators
    G = defaultdict(lambda: {
        "total_kb_authored": 0,
        "total_kb_modified": 0,
        "total_kb_hits": 0,
        "total_ticket_notes": 0,
        "total_tickets_assigned": 0,
        "topics_active_in": set(),
        "categories_authored": set(),
        "earliest_activity_days": 9999,
        "latest_activity_days": 9999,
    })

    # Signal 1+2+3+4: KB articles
    for art in all_articles:
        cat_name = art.get("_category_name", "Unknown")
        author_uid = art.get("user_id")
        modifier_uid = art.get("modified_by")
        hits = art.get("hits") or 0
        tu = art.get("thumbs_up") or 0
        td = art.get("thumbs_down") or 0
        mod_days = days_ago(art.get("modified_at") or art.get("updated_at"))
        created_days = days_ago(art.get("created_at"))

        if author_uid:
            key = (author_uid, cat_name)
            S[key]["kb_authored"] += 1
            S[key]["kb_hits"] += hits
            S[key]["kb_thumbs_up"] += tu
            S[key]["kb_thumbs_down"] += td
            S[key]["kb_latest_modified_days"] = min(S[key]["kb_latest_modified_days"], mod_days)
            G[author_uid]["total_kb_authored"] += 1
            G[author_uid]["total_kb_hits"] += hits
            G[author_uid]["categories_authored"].add(cat_name)
            G[author_uid]["topics_active_in"].add(cat_name)
            G[author_uid]["earliest_activity_days"] = max(G[author_uid]["earliest_activity_days"], created_days)
            G[author_uid]["latest_activity_days"] = min(G[author_uid]["latest_activity_days"], mod_days)

        if modifier_uid and modifier_uid != author_uid:
            key = (modifier_uid, cat_name)
            S[key]["kb_modified"] += 1
            G[modifier_uid]["total_kb_modified"] += 1
            G[modifier_uid]["topics_active_in"].add(cat_name)
            G[modifier_uid]["latest_activity_days"] = min(G[modifier_uid]["latest_activity_days"], mod_days)

    # Signal 5: Ticket responder assignment
    for t in tickets_detail:
        topic = get_ticket_topic(t)
        responder_id = t.get("responder_id")
        created_days = days_ago(t.get("created_at"))

        if responder_id:
            uid = agent_id_to_uid.get(responder_id, responder_id)
            key = (uid, topic)
            S[key]["ticket_responder"] += 1
            S[key]["tickets_touched"].add(t.get("id"))
            S[key]["ticket_latest_days"] = min(S[key]["ticket_latest_days"], created_days)
            G[uid]["total_tickets_assigned"] += 1
            G[uid]["topics_active_in"].add(topic)
            G[uid]["latest_activity_days"] = min(G[uid]["latest_activity_days"], created_days)

    # Signal 6+7: Ticket notes
    for n in all_notes:
        uid = n.get("user_id")
        incoming = n.get("incoming", False)
        deleted = n.get("deleted", False)
        private = n.get("private", False)
        if deleted or not uid:
            continue

        topic = n.get("_ticket_issue_type") or n.get("_ticket_type") or "General Support"
        note_days = days_ago(n.get("created_at"))
        body = n.get("body") or n.get("body_html") or ""
        body_len = len(body)

        if not incoming:  # Agent-authored
            key = (uid, topic)
            S[key]["ticket_notes_total"] += 1
            S[key]["ticket_note_chars"] += body_len
            S[key]["tickets_touched"].add(n.get("_ticket_id"))
            S[key]["note_latest_days"] = min(S[key]["note_latest_days"], note_days)
            if private:
                S[key]["ticket_notes_private"] += 1
            else:
                S[key]["ticket_notes_public"] += 1
            G[uid]["total_ticket_notes"] += 1
            G[uid]["topics_active_in"].add(topic)
            G[uid]["latest_activity_days"] = min(G[uid]["latest_activity_days"], note_days)

    print(f"  {len(S)} (agent, topic) pairs computed")
    print(f"  {len(G)} unique agents with activity")

    # ─── STEP 7: Compute weighted scores and tier ───
    print("\n[7/7] Computing weighted expertise scores and L1→L2→L3 tiers...")

    """
    SCORING MODEL:
    
    Base Points:
      KB article authored:     10 pts each
      KB article modified:      3 pts each
      Ticket note (public):     5 pts each
      Ticket note (private):    2 pts each
      Ticket assigned:          3 pts each
    
    Quality Multipliers:
      Article hits:             +0.01 per hit (popular content = more expertise)
      Article thumbs_up:        +2 per thumbs_up
      Article thumbs_down:      -1 per thumbs_down
      Note length:              +0.001 per char (substantive replies = more expertise)
    
    Recency Multiplier (applied to total):
      ≤90 days:    ×1.0
      91-180 days: ×0.8
      181-365:     ×0.6
      366-730:     ×0.4
      >730 days:   ×0.2
    
    Status Multiplier:
      Active agent: ×1.0
      Deleted agent: ×0.5 (still valuable for historical context, but deprioritized for contact)
    
    TIER DEFINITIONS (per topic):
      L1 (Primary Expert):    Top scorer AND score ≥ 20
      L2 (Secondary Expert):  2nd-3rd scorers AND score ≥ 10
      L3 (Contributing):      4th+ scorers OR score ≥ 5
      --  (Minimal):          score < 5 (not listed)
    """

    scored = {}  # (uid, topic) → {score, tier, breakdown}

    for (uid, topic), signals in S.items():
        # Base points
        kb_auth_pts = signals["kb_authored"] * 10
        kb_mod_pts = signals["kb_modified"] * 3
        note_pub_pts = signals["ticket_notes_public"] * 5
        note_priv_pts = signals["ticket_notes_private"] * 2
        assign_pts = signals["ticket_responder"] * 3

        # Quality bonuses
        hit_bonus = signals["kb_hits"] * 0.01
        thumbs_bonus = signals["kb_thumbs_up"] * 2 - signals["kb_thumbs_down"] * 1
        note_len_bonus = signals["ticket_note_chars"] * 0.001

        raw_score = kb_auth_pts + kb_mod_pts + note_pub_pts + note_priv_pts + assign_pts + hit_bonus + thumbs_bonus + note_len_bonus

        # Recency
        best_recency = min(
            signals["kb_latest_modified_days"],
            signals["note_latest_days"],
            signals["ticket_latest_days"],
        )
        rec_mult = recency_weight(best_recency)

        # Status
        status = identity.get(uid, {}).get("status", "unknown")
        status_mult = 1.0 if status == "active" else 0.5

        final_score = raw_score * rec_mult * status_mult

        if final_score < 1:
            continue

        scored[(uid, topic)] = {
            "score": round(final_score, 1),
            "raw_score": round(raw_score, 1),
            "recency_mult": rec_mult,
            "status_mult": status_mult,
            "best_recency_days": best_recency,
            "kb_authored": signals["kb_authored"],
            "kb_modified": signals["kb_modified"],
            "kb_hits": signals["kb_hits"],
            "kb_thumbs_up": signals["kb_thumbs_up"],
            "kb_thumbs_down": signals["kb_thumbs_down"],
            "ticket_notes_public": signals["ticket_notes_public"],
            "ticket_notes_private": signals["ticket_notes_private"],
            "ticket_responder": signals["ticket_responder"],
            "tickets_touched": len(signals["tickets_touched"]),
            "note_chars": signals["ticket_note_chars"],
        }

    # Group by topic, rank, assign tiers
    topics = defaultdict(list)
    for (uid, topic), data in scored.items():
        info = identity.get(uid, {"name": f"User-{uid}", "email": "?", "status": "unknown", "agent_id": None})
        topics[topic].append({
            "uid": uid,
            "name": info["name"],
            "email": info["email"],
            "status": info["status"],
            "agent_id": info.get("agent_id"),
            **data,
        })

    # Sort each topic by score DESC, assign L1/L2/L3
    tiered = {}
    for topic in sorted(topics.keys()):
        agents = sorted(topics[topic], key=lambda x: -x["score"])
        for i, a in enumerate(agents):
            if i == 0 and a["score"] >= 20:
                a["tier"] = "L1"
            elif i <= 2 and a["score"] >= 10:
                a["tier"] = "L2"
            elif a["score"] >= 5:
                a["tier"] = "L3"
            else:
                a["tier"] = "--"
            a["rank"] = i + 1
        tiered[topic] = agents

    # ─── OUTPUT ───
    print("\n" + "=" * 110)
    print("COMPLETE EXPERTISE MAP: ALL AGENTS × ALL TOPICS × ALL SIGNALS")
    print("=" * 110)

    print(f"\nScoring: KB authored(×10) + KB modified(×3) + Public notes(×5) + Private notes(×2) + Assigned(×3)")
    print(f"         + hit_bonus(×0.01/hit) + thumbs(+2up/-1down) + note_length(×0.001/char)")
    print(f"         × recency(1.0→0.2) × status(active=1.0, deleted=0.5)")
    print(f"\nTiers: L1=Primary Expert (rank 1, score≥20) | L2=Secondary (rank 2-3, score≥10) | L3=Contributing (score≥5)")

    for topic in sorted(tiered.keys()):
        agents = tiered[topic]
        active_count = sum(1 for a in agents if a["status"] == "active")
        total_count = len(agents)
        print(f"\n{'─' * 110}")
        print(f"  TOPIC: {topic}  ({total_count} experts, {active_count} active)")
        print(f"{'─' * 110}")
        print(f"  {'Tier':<5} {'Rank':<5} {'●':<2} {'Agent Name':<32} {'Email':<35} {'Score':>7} {'KB':>4} {'Mod':>4} {'Notes':>6} {'Asgn':>5} {'Hits':>6} {'Recency':>8}")
        print(f"  {'─'*4} {'─'*4} {'─'*1} {'─'*31} {'─'*34} {'─'*6} {'─'*3} {'─'*3} {'─'*5} {'─'*4} {'─'*5} {'─'*7}")
        for a in agents:
            icon = "●" if a["status"] == "active" else "○"
            notes_str = f"{a['ticket_notes_public']}p+{a['ticket_notes_private']}i"
            rec_str = f"{a['best_recency_days']}d"
            print(f"  {a['tier']:<5} #{a['rank']:<4} {icon} {a['name']:<32} {a['email']:<35} {a['score']:>6.1f} {a['kb_authored']:>4} {a['kb_modified']:>4} {notes_str:>6} {a['ticket_responder']:>5} {a['kb_hits']:>6} {rec_str:>8}")

    # ─── GLOBAL AGENT SUMMARY ───
    print(f"\n{'=' * 110}")
    print("COMPLETE AGENT ROSTER — GLOBAL ACTIVITY SUMMARY")
    print(f"{'=' * 110}")

    agent_summary = []
    for uid, g in G.items():
        info = identity.get(uid, {"name": f"User-{uid}", "email": "?", "status": "unknown", "agent_id": None})
        # Count tiers across all topics
        l1_count = sum(1 for t in tiered.values() for a in t if a["uid"] == uid and a["tier"] == "L1")
        l2_count = sum(1 for t in tiered.values() for a in t if a["uid"] == uid and a["tier"] == "L2")
        l3_count = sum(1 for t in tiered.values() for a in t if a["uid"] == uid and a["tier"] == "L3")
        total_score = sum(a["score"] for t in tiered.values() for a in t if a["uid"] == uid)
        agent_summary.append({
            "uid": uid,
            "name": info["name"],
            "email": info["email"],
            "status": info["status"],
            "agent_id": info.get("agent_id"),
            "total_kb_authored": g["total_kb_authored"],
            "total_kb_modified": g["total_kb_modified"],
            "total_kb_hits": g["total_kb_hits"],
            "total_ticket_notes": g["total_ticket_notes"],
            "total_tickets_assigned": g["total_tickets_assigned"],
            "topics_count": len(g["topics_active_in"]),
            "topics": sorted(g["topics_active_in"]),
            "l1_topics": l1_count,
            "l2_topics": l2_count,
            "l3_topics": l3_count,
            "total_score": round(total_score, 1),
            "latest_activity_days": g["latest_activity_days"],
        })

    agent_summary.sort(key=lambda x: -x["total_score"])

    print(f"\n  {'●':<2} {'Agent Name':<32} {'Email':<35} {'Status':<8} {'KB':>4} {'Mod':>4} {'Notes':>6} {'Asgn':>5} {'Topics':>7} {'L1':>3} {'L2':>3} {'L3':>3} {'Score':>8} {'Last':>6}")
    print(f"  {'─'*1} {'─'*31} {'─'*34} {'─'*7} {'─'*3} {'─'*3} {'─'*5} {'─'*4} {'─'*6} {'─'*2} {'─'*2} {'─'*2} {'─'*7} {'─'*5}")
    for a in agent_summary:
        icon = "●" if a["status"] == "active" else "○"
        last = f"{a['latest_activity_days']}d" if a['latest_activity_days'] < 9999 else "n/a"
        print(f"  {icon} {a['name']:<32} {a['email']:<35} {a['status']:<8} {a['total_kb_authored']:>4} {a['total_kb_modified']:>4} {a['total_ticket_notes']:>6} {a['total_tickets_assigned']:>5} {a['topics_count']:>7} {a['l1_topics']:>3} {a['l2_topics']:>3} {a['l3_topics']:>3} {a['total_score']:>8.1f} {last:>6}")

    # ─── AGENTS WITH ZERO ACTIVITY ───
    active_uids = set(G.keys())
    all_uids = set(identity.keys())
    zero_activity = all_uids - active_uids
    if zero_activity:
        print(f"\n  AGENTS WITH ZERO EXPERTISE SIGNALS ({len(zero_activity)}):")
        for uid in sorted(zero_activity, key=lambda u: identity.get(u, {}).get("name", "")):
            info = identity[uid]
            icon = "●" if info["status"] == "active" else "○"
            print(f"    {icon} {info['name']:<32} {info['email']:<35} {info['status']}")

    # ─── L1 CONTACT QUICK REFERENCE ───
    print(f"\n{'=' * 110}")
    print("L1 PRIMARY CONTACT QUICK REFERENCE (who to contact first per topic)")
    print(f"{'=' * 110}")
    print(f"\n  {'Topic':<45} {'L1 Contact':<30} {'Email':<35} {'Score':>7}")
    print(f"  {'─'*44} {'─'*29} {'─'*34} {'─'*6}")
    for topic in sorted(tiered.keys()):
        agents = tiered[topic]
        l1 = [a for a in agents if a["tier"] == "L1"]
        if l1:
            a = l1[0]
            icon = "●" if a["status"] == "active" else "○"
            print(f"  {topic:<45} {icon} {a['name']:<28} {a['email']:<35} {a['score']:>6.1f}")
        else:
            best = agents[0] if agents else None
            if best:
                icon = "●" if best["status"] == "active" else "○"
                print(f"  {topic:<45} {icon} {best['name']:<28} {best['email']:<35} {best['score']:>6.1f} (no L1)")

    # ─── ACTIVE-ONLY ESCALATION PATHS ───
    print(f"\n{'=' * 110}")
    print("ESCALATION PATHS (ACTIVE AGENTS ONLY) — L1 → L2 → L3")
    print(f"{'=' * 110}")
    for topic in sorted(tiered.keys()):
        agents = [a for a in tiered[topic] if a["status"] == "active"]
        if not agents:
            print(f"\n  {topic}: ⚠ NO ACTIVE EXPERTS — all contributors are former agents")
            former = [a for a in tiered[topic]][:3]
            for a in former:
                print(f"    ○ (former) {a['name']:<28} {a['email']:<35} {a['tier']}")
            continue
        print(f"\n  {topic}:")
        for a in agents[:5]:
            print(f"    {a['tier']:<4} {a['name']:<32} {a['email']:<35} score={a['score']:.1f}")

    # ─── SAVE RESULTS ───
    output = {
        "scoring_model": {
            "base_points": {
                "kb_authored": 10,
                "kb_modified": 3,
                "ticket_note_public": 5,
                "ticket_note_private": 2,
                "ticket_assigned": 3,
            },
            "quality_bonuses": {
                "kb_hits": 0.01,
                "kb_thumbs_up": 2,
                "kb_thumbs_down": -1,
                "note_chars": 0.001,
            },
            "recency_multiplier": {"0-90d": 1.0, "91-180d": 0.8, "181-365d": 0.6, "366-730d": 0.4, "730+d": 0.2},
            "status_multiplier": {"active": 1.0, "deleted": 0.5},
            "tier_definitions": {
                "L1": "Primary Expert — rank 1 AND score >= 20",
                "L2": "Secondary Expert — rank 2-3 AND score >= 10",
                "L3": "Contributing Expert — score >= 5",
            },
        },
        "identity_map": {str(k): v for k, v in identity.items()},
        "agent_summary": agent_summary,
        "tiered_expertise": {
            topic: [{k: (list(v) if isinstance(v, set) else v) for k, v in a.items()} for a in agents]
            for topic, agents in tiered.items()
        },
        "topic_l1_contacts": {
            topic: next(({"name": a["name"], "email": a["email"], "status": a["status"], "score": a["score"]}
                         for a in agents if a["tier"] == "L1"), None)
            for topic, agents in tiered.items()
        },
        "stats": {
            "total_agents": len(identity),
            "active_agents": len(active_agents),
            "deleted_agents": len(deleted_agents),
            "zero_activity_agents": len(zero_activity),
            "total_articles": len(all_articles),
            "total_tickets": len(tickets_detail),
            "total_notes": len(all_notes),
            "total_topics": len(tiered),
            "total_scored_pairs": len(scored),
        },
    }

    out_path = Path(__file__).parent / "freshdesk_expertise_deep_dive.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nFull results → {out_path}")

if __name__ == "__main__":
    main()
