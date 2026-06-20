import csv
import getpass
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from playwright.sync_api import (
    Locator,
    Page,
    Playwright,
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent
CSV_FIELDS = ["name", "title", "time"]
ACCEPT_CSV = PROJECT_DIR / "accept.csv"
CONNECT_CSV = PROJECT_DIR / "connect.csv"

ACCEPT_RE = re.compile(r"^\s*Accept\b", re.IGNORECASE)
CONNECT_RE = re.compile(r"^\s*Connect\b", re.IGNORECASE)
SEND_RE = re.compile(r"^Send(\s+now)?(\s|$)", re.IGNORECASE)
DONE_RE = re.compile(r"^Done(\s|$)", re.IGNORECASE)

NOISE_RE = re.compile(
    r"^(Accept|Ignore|Connect|Follow|Message|More|Send|Send now|Done|Pending|Cancel|Dismiss)$",
    re.IGNORECASE,
)

TITLE_SELECTORS = [
    "div.invitation-card__subtitle",
    "div.artdeco-entity-lockup__subtitle",
    "span.entity-result__primary-subtitle",
    "p.entity-result__summary",
    "div.discover-entity-type-card__subtitle",
    "a[href*='/in/'] ~ div span",
]

WS_TITLE_XPATHS = [
    f"//*[@id=\"workspace\"]/div/div/div/div[2]/div/section/div/div/div/div[1]/div[1]/div/div[{i}]/div/div/a/div/div[1]/div[{i}]/div[1]/p/span"
    for i in range(1, 11)
]

TITLE_SELECTORS.extend(WS_TITLE_XPATHS)

# ANSI colour helpers
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BLACK = "\033[30m"
    BG_GREEN = "\033[42m"
    BG_CYAN = "\033[46m"
    BG_YELLOW = "\033[43m"
    BG_RED = "\033[41m"


if os.name == "nt":
    os.system("")  # enable VT100 on Windows


# -----------------------------------------------------------------------------
# Data model
# -----------------------------------------------------------------------------
@dataclass
class Person:
    name: str = ""
    title: str = ""
    element: Optional[Locator] = field(default=None, repr=False)

    @property
    def display_name(self) -> str:
        return self.name or "(unknown)"

    @property
    def display_title(self) -> str:
        return self.title or "(no title)"


# -----------------------------------------------------------------------------
# CSV helpers
# -----------------------------------------------------------------------------
def ensure_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def append_csv(path: Path, person: Person, when: Optional[datetime] = None) -> None:
    ensure_csv(path)
    when = when or datetime.now().astimezone()
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(
            {
                "name": person.name,
                "title": person.title,
                "time": when.isoformat(sep=" ", timespec="seconds"),
            }
        )


# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------
def badge(label: str, bg: str) -> str:
    return f"{C.BOLD}{bg}{C.BLACK} {label} {C.RESET}"


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S · %d %b %Y")


def print_action(action: str, bg: str, person: Person, when: Optional[datetime] = None) -> None:
    when = when or datetime.now().astimezone()
    print(
        f"{badge(action, bg)}  {C.BOLD}{C.WHITE}{person.display_name}{C.RESET} "
        f"{C.DIM}│{C.RESET} {C.YELLOW}{person.display_title}{C.RESET} "
        f"{C.DIM}│{C.RESET} {C.DIM}{C.CYAN}{fmt_time(when)}{C.RESET}",
        flush=True,
    )


# -----------------------------------------------------------------------------
# Text extraction helpers
# -----------------------------------------------------------------------------
def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def name_from_aria(label: str) -> str:
    label = clean_text(label)
    if not label:
        return ""
    for pattern in (
        r"Invite\s+(.*?)\s+to\s+connect",
        r"Connect\s+with\s+(.*)$",
        r"Accept\s+invitation\s+from\s+(.*)$",
        r"Accept\s+(.*?)'?s\b",
        r"Accept\s+(.*)$",
    ):
        m = re.search(pattern, label, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(" .")
    return ""


def closest_card(button: Locator) -> Optional[Locator]:
    """Find the smallest useful card container for a given button."""
    for selector in (
        "xpath=ancestor::li[contains(@class,'invitation-card')][1]",
        "xpath=ancestor::li[contains(@class,'mn-discovery')][1]",
        "xpath=ancestor::div[contains(@class,'entity-result__item')][1]",
        "xpath=ancestor::li[1]",
        "xpath=ancestor::article[1]",
        "xpath=ancestor-or-self::div[@data-view-name][1]",
        "xpath=ancestor::div[contains(@class,'artdeco-card')][1]",
        "xpath=ancestor::div[contains(@class,'artdeco-entity-lockup')][1]",
        "xpath=ancestor::div[4]",
        "xpath=ancestor::div[3]",
        "xpath=ancestor::div[2]",
        "xpath=ancestor::div[1]",
    ):
        try:
            loc = button.locator(selector)
            if loc.count() > 0:
                return loc.first
        except Exception:
            continue
    return None


def _card_lines(card: Locator) -> list[str]:
    try:
        text = card.inner_text()
    except Exception:
        return []

    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = clean_text(raw)
        if not line or NOISE_RE.fullmatch(line):
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def _is_name_like(text: str, name: str) -> bool:
    a, b = text.casefold(), name.casefold()
    return a == b or a.startswith(b) or b.startswith(a)


def extract_person(button: Locator, page: Page) -> Person:
    """Extract name and title from the card containing ``button``."""
    person = Person(element=button)

    try:
        aria_label = button.get_attribute("aria-label") or ""
    except Exception:
        aria_label = ""
    name_from_label = name_from_aria(aria_label)

    card = closest_card(button)
    if card is None:
        person.name = name_from_label
        return person

    # Name: prefer aria-label (always clean), fall back to profile link text.
    person.name = name_from_label
    if not person.name:
        try:
            profile_link = card.locator("a[href*='/in/']").first
            if profile_link.count() > 0:
                raw = clean_text(profile_link.inner_text())
                if raw:
                    for noise in (" and ", " is a ", " mutual ", " connection", " Connect"):
                        idx = raw.lower().find(noise.lower())
                        if idx != -1:
                            raw = raw[:idx].strip()
                    raw = re.split(r"[\U0001F300-\U0010FFFF\u2600-\u27BF]", raw, maxsplit=1)[0].strip()
                    if raw:
                        person.name = raw
        except Exception:
            pass

    if person.name:
        person.name = person.name.title()

    # Title: try well-known subtitle selectors first.
    for selector in TITLE_SELECTORS:
        try:
            candidates = card.locator(selector)
            for i in range(min(candidates.count(), 5)):
                t = clean_text(candidates.nth(i).inner_text())
                if t and not NOISE_RE.fullmatch(t) and t.casefold() != person.name.casefold() and not _is_name_like(t, person.name):
                    person.title = t
                    break
        except Exception:
            continue
        if person.title:
            break

    return person


def title_matches(title: str, keywords: list[str]) -> bool:
    """Return True if the title contains any of the keywords (case-insensitive)."""
    if not keywords:
        return True
    title_lower = title.casefold()
    return any(kw in title_lower for kw in keywords)


# -----------------------------------------------------------------------------
# Interaction helpers
# -----------------------------------------------------------------------------
def safe_click(locator: Locator, timeout: int = 3000) -> bool:
    """Click an element, falling back to a JavaScript click on timeout."""
    try:
        locator.click(timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        try:
            locator.evaluate("el => el.click()")
            return True
        except Exception:
            return False
    except Exception:
        return False


def handle_connect_modal(page: Page) -> None:
    """Dismiss the 'Add a note' / confirmation modal after clicking Connect."""
    for btn_re in (SEND_RE, DONE_RE):
        buttons = page.get_by_role("button", name=btn_re)
        for i in range(min(buttons.count(), 3)):
            if safe_click(buttons.nth(i), timeout=2000):
                page.wait_for_timeout(200)
                return


def scroll_page(page: Page, distance: int = 1200) -> None:
    try:
        page.evaluate(f"window.scrollBy(0, {distance})")
    except Exception:
        page.mouse.wheel(0, distance)
    page.wait_for_timeout(500)


def is_limit_banner_visible(page: Page) -> bool:
    return page.locator("text=/weekly invitation limit/i").count() > 0


# -----------------------------------------------------------------------------
# Main automation logic
# -----------------------------------------------------------------------------
class LinkedInAutomation:
    def __init__(
        self,
        page: Page,
        *,
        max_connect: Optional[int] = None,
        keywords: Optional[list[str]] = None,
        connect_refresh_every: int = 20,
        max_total_clicks: int = 2000,
        max_scroll_attempts: int = 30,
    ) -> None:
        self.page = page
        self.max_connect = max_connect
        self.keywords = keywords or []
        self.connect_refresh_every = connect_refresh_every
        self.max_total_clicks = max_total_clicks
        self.max_scroll_attempts = max_scroll_attempts

        self.accept_clicked = 0
        self.connect_clicked = 0
        self.total_clicks = 0
        self.connect_since_refresh = 0
        self.skip_since_refresh = 0
        self.scroll_attempts = 0

    # ------------------------------------------------------------------
    def run(self) -> tuple[int, int]:
        while self.total_clicks < self.max_total_clicks:
            if self._try_accept():
                continue

            if self.max_connect is not None and self.connect_clicked >= self.max_connect:
                logger.info("Reached the requested Connect limit.")
                break

            if self._try_connect():
                continue

            if self._try_connect_by_invite_link():
                continue

            if self.scroll_attempts >= self.max_scroll_attempts:
                logger.info("No more actionable cards after several scroll attempts.")
                break

            self._scroll()

        return self.accept_clicked, self.connect_clicked

    # ------------------------------------------------------------------
    def _find_buttons(self, regex: re.Pattern) -> list[Locator]:
        """Collect concrete Locator handles for all matching buttons."""
        buttons: list[Locator] = []
        role = self.page.get_by_role("button", name=regex)
        text = self.page.locator("button").filter(has_text=regex)
        for base in (role, text):
            for i in range(base.count()):
                buttons.append(base.nth(i))
        return buttons

    def _try_accept(self) -> bool:
        for btn in self._find_buttons(ACCEPT_RE):
            person = extract_person(btn, self.page)
            if safe_click(btn):
                append_csv(ACCEPT_CSV, person)
                print_action("ACCEPT ", C.BG_GREEN, person)
                self.accept_clicked += 1
                self.total_clicks += 1
                self.scroll_attempts = 0
                self.page.wait_for_timeout(300)
                return True
        return False

    def _try_connect_by_invite_link(self) -> bool:
        links = self.page.get_by_role("link", name=re.compile(r"^Invite .+ to connect$", re.IGNORECASE))
        for i in range(links.count()):
            link = links.nth(i)
            try:
                label = link.get_attribute("aria-label") or link.get_attribute("title") or ""
            except Exception:
                label = ""
            name = name_from_aria(label) or ""
            link.click()
            time.sleep(1)
            send_btn = self.page.get_by_role("button", name=re.compile(r"^Send without a note$", re.IGNORECASE))
            if send_btn.count() > 0:
                send_btn.click()
                person = Person(name=name)
                append_csv(CONNECT_CSV, person)
                print_action("CONNECT", C.BG_CYAN, person)
                self.connect_clicked += 1
                self.total_clicks += 1
                self.scroll_attempts = 0
                self.page.wait_for_timeout(400)
                return True
        return False

    def _try_connect(self) -> bool:
        buttons = self._find_buttons(CONNECT_RE)
        skipped_any = False
        s = 0 
        for btn in buttons:
            person = extract_person(btn, self.page)

            if self.keywords and not title_matches(person.title, self.keywords):
                skipped_any = True
                s+=1
                print_action(" SKIP  ", C.BG_YELLOW, person)
                self.skip_since_refresh += 1
                if self.connect_refresh_every > 0 and self.skip_since_refresh >= self.connect_refresh_every:
                    self._refresh()
                continue

            if safe_click(btn):
                append_csv(CONNECT_CSV, person)
                print_action("CONNECT", C.BG_CYAN, person)
                handle_connect_modal(self.page)

                self.connect_clicked += 1
                self.connect_since_refresh += 1
                self.total_clicks += 1
                self.scroll_attempts = 0
                s+=1

                if is_limit_banner_visible(self.page):
                    logger.warning("LinkedIn weekly invitation limit reached. Stopping.")
                    return True  # Will exit on next loop iteration

                if self.connect_refresh_every > 0 and self.connect_since_refresh >= self.connect_refresh_every:
                    self._refresh()
                else:
                    self.page.wait_for_timeout(400)
                return True
            print(s)

        # If we skipped every visible card because of keywords, keep scrolling
        # to look for matching ones (unless there were no cards at all).
        if not buttons:
            return False
        return skipped_any  # True => we found cards, just not matching; keep scrolling

    def _scroll(self) -> None:
        scroll_page(self.page)
        self.scroll_attempts += 1

    def _refresh(self) -> None:
        logger.info("Refreshing the page to keep the feed alive...")
        self.page.reload(wait_until="domcontentloaded")
        self.connect_since_refresh = 0
        self.skip_since_refresh = 0
        self.scroll_attempts = 0
        self.page.wait_for_timeout(1200)


# -----------------------------------------------------------------------------
# Login flow
# -----------------------------------------------------------------------------
def linkedin_login(page: Page) -> bool:

    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
#
    if not email:
        email = input("LinkedIn email: ").strip()
    if not password:
        password = getpass.getpass("LinkedIn password: ")

    if not email or not password:
        logger.error("Email and password are required.")
        return False
    
    page.get_by_role("textbox", name="Email or phone").fill(email)
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("textbox", name="Password").press("Enter")

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    if "checkpoint/challenge" in page.url:
        logger.warning("LinkedIn checkpoint detected. Attempting to bypass...")

        # Try clicking reCAPTCHA checkbox if present
        try:
            recaptcha = page.frame_locator("iframe[src*='recaptcha']").first
            recaptcha.locator(".recaptcha-checkbox").click(timeout=5000)
            logger.info("Clicked reCAPTCHA checkbox — solve it manually in the browser.")
        except Exception:
            pass

        # Wait a moment for any challenge to settle
        page.wait_for_timeout(3000)

        # If still on challenge page, check for verification code flow
        if "checkpoint/challenge" in page.url:
            try:
                heading = page.get_by_role(
                    "heading",
                    name=re.compile(r"How do you want to receive your verification code\?", re.IGNORECASE),
                ).text_content()
                logger.info("Verification method: %s", heading)
            except Exception:
                pass

            # Check if there's a reCAPTCHA challenge visible (wait for manual solve)
            try:
                page.wait_for_selector("iframe[src*='recaptcha']", timeout=3000)
                logger.info("reCAPTCHA detected. Please solve it in the browser window, then press Enter...")
                input("Press Enter after solving the captcha...")
            except Exception:
                pass

            # If still on challenge page, try verification code
            if "checkpoint/challenge" in page.url:
                try:
                    code = input("Enter the verification code you received: ").strip()
                    page.get_by_role("spinbutton", name="Verification code").fill(code)
                    page.get_by_role("button", name=re.compile(r"Submit", re.IGNORECASE)).click()
                    page.wait_for_load_state("domcontentloaded")
                except Exception:
                    pass

        # Final wait for page to settle
        page.wait_for_timeout(2000)

    return "/login" not in page.url


# -----------------------------------------------------------------------------
# Prompts / environment
# -----------------------------------------------------------------------------
def read_connect_limit() -> Optional[int]:
    raw = (os.getenv("CONNECT_LIMIT") or "").strip()
    if not raw:
        raw = input("How many Connect clicks do you need? (Enter = no limit): ").strip()
    if not raw:
        return None
    try:
        value = int(raw)
        if value < 0:
            logger.warning("Negative limit ignored; running with no limit.")
            return None
        return value
    except ValueError:
        logger.warning("Invalid number; running with no limit.")
        return None


def read_title_keywords() -> tuple[list[str], Optional[str]]:
    raw = (os.getenv("TITLE_KEYWORD") or "").strip()
    if not raw:
        raw = input(
            "Title keyword filter — only Connect when title contains this "
            "(comma-separated, Enter = no filter): "
        ).strip()
    if not raw:
        return [], None

    from urllib.parse import urlparse, parse_qs, quote

    search_url = None
    if raw.startswith("http://") or raw.startswith("https://"):
        search_url = raw
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        kw_param = params.get("keywords", [])
        if kw_param:
            raw = kw_param[0]
        else:
            return [], search_url
    else:
        search_url = "https://www.linkedin.com/search/results/people/?keywords=" + quote(raw)

    keywords = [kw.strip().casefold() for kw in raw.split(",") if kw.strip()]
    if keywords:
        logger.info(
            "%s Filter active: %s",
            badge("FILTER ", C.BG_YELLOW),
            ", ".join(f'"{kw}"' for kw in keywords),
        )
    return keywords, search_url


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(
        channel="msedge",
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    try:
        page.goto(
            "https://www.linkedin.com/login/en-us/?trk=guest_homepage-basic_nav-header-signin",
            wait_until="domcontentloaded",
        )
    
    
        while '/login'  in page.url:
            
            linkedin_login(page) 
            page.wait_for_timeout(2500)
            
        title_keywords, search_url = read_title_keywords()
        target_url = search_url or "https://www.linkedin.com/mynetwork/invitation-manager/received/"
        max_connect = read_connect_limit()

        max_total = 2000
        if max_connect is not None:
            max_total = max(2000, max_connect + 200)

        base_search_url = None
        if search_url:
            from urllib.parse import urlparse, urlencode, parse_qs
            parsed = urlparse(search_url)
            params = parse_qs(parsed.query)
            params.pop("page", None)
            base_search_url = parsed._replace(query=urlencode(params, doseq=True)).geturl()

        page_num = 1
        total_accept = 0
        total_connect = 0
        connects_per_page = 10

        while True:
            if base_search_url:
                target_url = f"{base_search_url}&page={page_num}"
            page.goto(target_url, wait_until="domcontentloaded")

            print(f"\n{C.BOLD}{C.CYAN}{'─' * 64}{C.RESET}")
            print(f"  {C.BOLD}{C.WHITE}Starting LinkedIn automation …{C.RESET}")
            if title_keywords:
                print(f"  {C.DIM}Filter: title must contain → {', '.join(title_keywords)}{C.RESET}")
            if base_search_url:
                print(f"  {C.DIM}Page: {page_num}{C.RESET}")
            print(f"{C.BOLD}{C.CYAN}{'─' * 64}{C.RESET}\n")

            page_max = connects_per_page if base_search_url else max_connect
            automation = LinkedInAutomation(
                page,
                max_connect=page_max,
                keywords=title_keywords,
                connect_refresh_every=20,
                max_total_clicks=max_total,
            )
            accept_count, connect_count = automation.run()

            total_accept += accept_count
            total_connect += connect_count

            # Summary per page
            print(f"\n{C.BOLD}{C.CYAN}{'─' * 64}{C.RESET}")
            print(f"  {C.BOLD}{'Action':<14}{C.RESET}  {'Count':>6}")
            print(f"  {C.DIM}{'─' * 60}{C.RESET}")
            print(f"  {badge('ACCEPT ', C.BG_GREEN)}  {C.GREEN}{accept_count:>6}{C.RESET}   Page {page_num}")
            print(f"  {badge('CONNECT', C.BG_CYAN)}  {C.CYAN}{connect_count:>6}{C.RESET}   Page {page_num}")
            print(f"{C.BOLD}{C.CYAN}{'─' * 64}{C.RESET}\n")

            if not base_search_url:
                break

            if max_connect is not None and total_connect >= max_connect:
                logger.info("Reached total Connect limit. Stopping pagination.")
                break

            if connect_count < connects_per_page:
                logger.info("Page %d exhausted — no more connections found.", page_num)
                break

            page_num += 1

        # Final summary
        print(f"\n{C.BOLD}{C.CYAN}{'─' * 64}{C.RESET}")
        print(f"  {C.BOLD}{'Action':<14}{C.RESET}  {'Count':>6}   CSV file")
        print(f"  {C.DIM}{'─' * 60}{C.RESET}")
        print(
            f"  {badge('ACCEPT ', C.BG_GREEN)}  {C.GREEN}{total_accept:>6}{C.RESET}   "
            f"{C.DIM}{ACCEPT_CSV.name}{C.RESET}"
        )
        print(
            f"  {badge('CONNECT', C.BG_CYAN)}  {C.CYAN}{total_connect:>6}{C.RESET}   "
            f"{C.DIM}{CONNECT_CSV.name}{C.RESET}"
        )
        if title_keywords:
            print(f"  {C.DIM}Filter was: {', '.join(title_keywords)}{C.RESET}")
        if base_search_url:
            print(f"  {C.DIM}Pages scanned: 1–{page_num}{C.RESET}")
        print(f"{C.BOLD}{C.CYAN}{'─' * 64}{C.RESET}\n")

        if total_accept == 0 and total_connect == 0 and os.getenv("PW_SCREENSHOT_ON_ZERO", "0") == "1":
            page.screenshot(path="debug_last_page.png", full_page=True)
            logger.info("Saved screenshot: debug_last_page.png")

    finally:
        time.sleep(2)
        browser.close()


def main() -> None:
    with sync_playwright() as playwright:
        run(playwright)


if __name__ == "__main__":
    main()
