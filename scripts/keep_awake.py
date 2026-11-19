"""
Keep the live CareerLoom app awake.

Streamlit Community Cloud puts apps to sleep after a period with no visitors, and the next visitor sees a
"This app has gone to sleep" page. A scheduled GitHub Action (.github/workflows/keep-awake.yml) runs this script:
it opens the app in a headless browser like a real visitor, clicks the wake-up button if the app is asleep, and
waits until the app has loaded. No AI calls are made and no resume data is involved.

Usage: python scripts/keep_awake.py [url]
"""
import os
import sys

from playwright.sync_api import sync_playwright

APP_URL = "https://careerloom-ai.streamlit.app/"
WAKE_BUTTON = "Yes, get this app back up!"
LOADED_TEXT = "Tailor your resume"  # the hero heading on the main page


def app_loaded(page) -> bool:
    """Streamlit Cloud serves the app inside an iframe, so look in every frame for the app's heading."""
    for frame in page.frames:
        try:
            if frame.get_by_text(LOADED_TEXT).count():
                return True
        except Exception:
            pass  # frames can detach while the app starts up
    return False


def main(url: str) -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.getenv("KEEP_AWAKE_BROWSER_CHANNEL") or None)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(5_000)
            if "errors/not_found" in page.url:
                print("The app is not publicly visible (Streamlit says it doesn't exist or needs sign-in). "
                      "In share.streamlit.io, open the app's Settings > Sharing and make it public.")
                return 1

            wake = page.get_by_role("button", name=WAKE_BUTTON)
            if wake.count():
                print("App was asleep: waking it up.")
                wake.click()
            # A sleeping app takes a minute or two to start; a running one loads in seconds.
            for _ in range(80):
                if app_loaded(page):
                    print("App is awake and loaded.")
                    return 0
                page.wait_for_timeout(3_000)
            print("App did not finish loading in time. Check https://share.streamlit.io for errors.")
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else APP_URL))
