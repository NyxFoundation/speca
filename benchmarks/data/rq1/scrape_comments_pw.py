"""
Scrape Sherlock voting page comments using Playwright.

Usage:
  1. Run: uv run python3 benchmarks/data/rq1/scrape_comments_pw.py
  2. Browser opens → manually log in to Sherlock
  3. Press Enter in terminal to start scraping
  4. Output: benchmarks/data/rq1/sherlock_1140_comments.json

Session is saved to /tmp/chrome-sherlock so you only need to log in once.
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

NUMBERS = [
    68,69,70,71,72,73,75,76,78,79,81,82,83,84,85,86,87,88,89,90,
    93,96,97,98,99,100,101,102,104,105,106,114,116,119,120,131,
    136,137,139,140,142,143,146,152,153,155,157,158,160,162,164,
    165,168,170,172,173,175,177,179,180,184,187,188,189,191,193,
    195,196,197,198,199,200,201,202,204,206,213,214,215,221,223,
    224,225,227,230,232,237,238,240,245,246,248,249,254,256,262,
    263,266,268,269,270,272,273,274,275,276,277,278,279,280,281,
    283,284,285,287,288,291,293,294,296,298,299,300,301,302,303,
    304,305,306,307,310,311,312,313,318,320,321,322,324,325,327,
    328,329,330,332,333,334,335,336,337,339,340,341,342,344,346,
    347,348,352,353,357,358,359,360,361,362,363,364,365,366,367,
    368,369,370,374,375,377,378,379,380,383,384,385,386,387,388,
    390,391,392,393,394,395,396,397,398,399,400,401,402,403,404,
    405,406,407,408,409,410,411,412,413,414,
]

OUTPUT = Path(__file__).parent / "sherlock_1140_comments.json"
SESSION_DIR = "/tmp/chrome-sherlock"
BASE_URL = "https://audits.sherlock.xyz/contests/1140/voting"


def scrape():
    # Load existing progress (resume support)
    results = {}
    if OUTPUT.exists():
        with open(OUTPUT) as f:
            results = json.load(f)
        # Only keep entries that actually had comments (re-scrape empty ones)
        results = {k: v for k, v in results.items() if v}
        if results:
            print(f"Resuming: {len(results)} already have comments")

    remaining = [n for n in NUMBERS if str(n) not in results]
    if not remaining:
        print("All done!")
        return

    print(f"Will scrape {len(remaining)} issues.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            executable_path="/run/current-system/sw/bin/google-chrome-stable",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Navigate to Sherlock so user can log in
        page.goto("https://audits.sherlock.xyz/contests/1140", timeout=30000)
        print("=" * 60)
        print("Browser opened. Please log in to Sherlock.")
        print("Then navigate to a voting page, e.g.:")
        print(f"  {BASE_URL}/68")
        print("Waiting for login (checking every 10s)...")
        print("=" * 60)

        # Poll until we can access a voting page (login detected)
        test_url = f"{BASE_URL}/68"
        while True:
            try:
                page.goto(test_url, wait_until="networkidle", timeout=15000)
                # If we're on the voting page (not redirected), we're logged in
                current = page.url
                if "/voting/" in current:
                    print("Login detected! Starting scrape...\n")
                    break
                else:
                    print(f"  Not logged in yet (redirected to {current[:60]})")
            except Exception:
                print("  Page load timeout, retrying...")
            time.sleep(10)

        for i, n in enumerate(remaining):
            url = f"{BASE_URL}/{n}"
            print(f"[{i+1}/{len(remaining)}] #{n} ...", end=" ", flush=True)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)

                # Wait for discussion section
                try:
                    page.wait_for_selector(
                        '#discussion, [id^="discussion-comment-"]',
                        timeout=8000,
                    )
                except Exception:
                    pass

                # Scroll to bottom to trigger lazy-loaded comments
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)

                # Extract comments
                comments = page.evaluate("""() => {
                    const results = [];
                    const commentEls = document.querySelectorAll('[id^="discussion-comment-"]');
                    commentEls.forEach(el => {
                        const text = el.innerText.trim();
                        if (text) results.push(text);
                    });
                    if (results.length === 0) {
                        const disc = document.getElementById('discussion');
                        if (disc) {
                            const text = disc.innerText.trim();
                            if (text) results.push(text);
                        }
                    }
                    return results;
                }""")

                results[str(n)] = comments
                status = f"{len(comments)} comment(s)" if comments else "no comments"
                print(status)

            except Exception as e:
                print(f"ERROR: {e}")
                results[str(n)] = []

            # Save after each page
            with open(OUTPUT, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            time.sleep(0.5)

        context.close()

    with_comments = sum(1 for v in results.values() if v)
    print(f"\nDone! {with_comments}/{len(NUMBERS)} had comments.")
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    scrape()
