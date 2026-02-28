import os, re, json, sys
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.31sumai.com/attend/X2571/"
STATE_FILE = "state.json"

STATUS_CHARS = ["○", "◯", "△", "×", "－", "-"]

def post_discord(webhook: str, content: str):
    r = requests.post(webhook, json={"content": content}, timeout=30)
    r.raise_for_status()

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)

def extract_calendar(page) -> dict:
    body = page.inner_text("body")
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", body)
    month_key = "unknown"
    if m:
        month_key = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"

    table = page.locator("table.ui-datepicker-calendar")
    if table.count() == 0:
        raise RuntimeError("カレンダーテーブルが見つかりませんでした")

    cells = table.locator("td")
    results = {}

    for i in range(min(cells.count(), 800)):
        txt = cells.nth(i).inner_text().strip()
        if not txt:
            continue

        day_match = re.search(r"\b([1-9]|[12]\d|3[01])\b", txt)
        if not day_match:
            continue
        day = day_match.group(1)

        status = None
        for ch in STATUS_CHARS:
            if ch in txt:
                status = "－" if ch in ["－", "-"] else ch
                break

        if status:
            results[day] = status

    if not results:
        raise RuntimeError("日付とステータスが抽出できませんでした")

    return {month_key: results}

def diff(prev: dict, cur: dict):
    changes = []
    months = set(prev.keys()) | set(cur.keys())
    for month in sorted(months):
        p = prev.get(month, {})
        c = cur.get(month, {})
        days = set(p.keys()) | set(c.keys())
        for day in sorted(days, key=lambda x: int(x)):
            if p.get(day) != c.get(day):
                changes.append((month, day, p.get(day), c.get(day)))
    return changes

def main():
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("Missing DISCORD_WEBHOOK_URL", file=sys.stderr)
        sys.exit(1)

    prev_calendar = load_state().get("calendar", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("table.ui-datepicker-calendar", timeout=30000)

        cur_calendar = extract_calendar(page)
        browser.close()

    state = load_state()
    if "calendar" not in state:
        state["calendar"] = cur_calendar
        state["last_checked"] = datetime.utcnow().isoformat() + "Z"
        save_state(state)
        print("initialized")
        return

    changes = diff(prev_calendar, cur_calendar)
    if changes:
        lines = []
        for month, day, ps, cs in changes[:30]:
            lines.append(f"{month} {day}日: {ps or '（なし）'} → {cs or '（なし）'}")

        msg = "🔔 予約カレンダーの空き状況が更新されました\n" + URL + "\n\n" + "\n".join(lines)
        if len(changes) > 30:
            msg += f"\n…ほか {len(changes)-30} 件"

        post_discord(webhook, msg)

        state["calendar"] = cur_calendar
        state["last_checked"] = datetime.utcnow().isoformat() + "Z"
        save_state(state)
        print("changed")
    else:
        state["last_checked"] = datetime.utcnow().isoformat() + "Z"
        save_state(state)
        print("no change")

if __name__ == "__main__":
    main()
