import os, re, json, sys
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.31sumai.com/attend/X2571/"
STATE_FILE = "state.json"

def post_discord(webhook, content):
    requests.post(webhook, json={"content": content}, timeout=30)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def extract_calendar(page):

    body = page.inner_text("body")
    m = re.search(r"(\d{4})年\s*(\d{1,2})月", body)
    month_key = "unknown"
    if m:
        month_key = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"

    table = page.locator("table.ui-datepicker-calendar")
    cells = table.locator("td")

    results = {}

    for i in range(cells.count()):
        cell = cells.nth(i)

        text = cell.inner_text().strip()
        day_match = re.search(r"\b([1-9]|[12]\d|3[01])\b", text)
        if not day_match:
            continue
        day = day_match.group(1)

        classes = cell.get_attribute("class") or ""

        # 状態判定（クラスベース）
        if "ui-state-disabled" in classes:
            status = "－"
        elif "ui-datepicker-unselectable" in classes:
            status = "×"
        else:
            # クリック可能な日
            status = "○"

        results[day] = status

    if not results:
        raise RuntimeError("カレンダー取得失敗")

    return {month_key: results}

def diff(prev, cur):
    changes = []
    for month in set(prev.keys()) | set(cur.keys()):
        p = prev.get(month, {})
        c = cur.get(month, {})
        for day in set(p.keys()) | set(c.keys()):
            if p.get(day) != c.get(day):
                changes.append((month, day, p.get(day), c.get(day)))
    return changes

def main():

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        sys.exit("Webhook未設定")

    state = load_state()
    prev = state.get("calendar", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL)
        page.wait_for_selector("table.ui-datepicker-calendar", timeout=30000)

        cur = extract_calendar(page)
        browser.close()

    if "calendar" not in state:
        state["calendar"] = cur
        save_state(state)
        print("initialized")
        return

    changes = diff(prev, cur)

    if changes:
        lines = []
        for m, d, before, after in changes:
            lines.append(f"{m} {d}日: {before} → {after}")

        msg = "🔔 空き状況が変更されました\n" + URL + "\n\n" + "\n".join(lines)
        post_discord(webhook, msg)

        state["calendar"] = cur
        save_state(state)
        print("changed")
    else:
        print("no change")
post_discord(os.environ.get("DISCORD_WEBHOOK_URL"), "🔔 テスト通知です")
if __name__ == "__main__":
    main()
