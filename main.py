import csv
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Playwright, sync_playwright, expect
import os
import time
import getpass

# ── ANSI colour helpers ─────────────────────────────────────────────────────
class _C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_GREEN  = "\033[42m"
    BG_CYAN   = "\033[46m"
    BG_YELLOW = "\033[43m"
    BG_RED    = "\033[41m"
    BLACK     = "\033[30m"

if os.name == "nt":
    os.system("")  # enable VT100 on Windows


ACCEPT_RE = re.compile(r"^\s*Accept\b", re.IGNORECASE)
CONNECT_RE = re.compile(r"^\s*(Connect\b|Invite\b.*\bconnect\b)", re.IGNORECASE)
CONNECT_TEXT_RE = re.compile(r"^\s*Connect\b", re.IGNORECASE)

CSV_FIELDS = ["name", "title", "time"]
PROJECT_DIR = Path(__file__).resolve().parent
ACCEPT_CSV_PATH = PROJECT_DIR / "accept.csv"
CONNECT_CSV_PATH = PROJECT_DIR / "connect.csv"

IGNORE_CARD_LINE_RE = re.compile(
    r"^(Accept|Ignore|Connect|Follow|Message|More|Send|Send now|Done|Pending|Cancel|Dismiss)$",
    re.IGNORECASE,
)

# ── FIX: count_ cycles from 1 to 20, resetting to 1 after reaching 20 ──
count_ = 0  # Initialise at 0; will be incremented to 1 on first use


def _next_count() -> int:
    """Advance count_ through 1 → 2 → … → 20 → 1 → 2 → … and return it."""
    global count_
    count_ += 1
    if count_ > 20:
        count_ = 1
    return count_


def _fmt_time(dt: datetime) -> str:
    """Return a human-friendly timestamp like  14:07:32 · 01 Jun 2025"""
    return dt.strftime("%H:%M:%S · %d %b %Y")


def _ensure_csv_file(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()


def _append_csv_row(path: Path, row: dict[str, str]) -> None:
    is_new_file = (not path.exists()) or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if is_new_file:
            writer.writeheader()
        writer.writerow(row)


def _name_from_aria_label(label: str) -> str:
    label = re.sub(r"\s+", " ", label or "").strip()
    if not label:
        return ""

    patterns = [
        r"Invite\s+(.*?)\s+to\s+connect",
        r"Connect\s+with\s+(.*)$",
        r"Accept\s+invitation\s+from\s+(.*)$",
        r"Accept\s+(.*?)'?s\b",
        r"Accept\s+(.*)$",
    ]
    for pattern in patterns:
        m = re.search(pattern, label, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(" .")
    return ""


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _closest_card_container(button):
    # Try progressively shallower ancestors; prefer li/article (full card)
    # over an immediate div (which may be too narrow to contain the title).
    for xpath in (
        "xpath=ancestor::li[1]",
        "xpath=ancestor::article[1]",
        "xpath=ancestor-or-self::div[@data-view-name][1]",
        # Walk up to a div that contains BOTH the profile link and the action buttons;
        # these tend to be at least 4 levels above the button.
        "xpath=ancestor::div[4]",
        "xpath=ancestor::div[3]",
        "xpath=ancestor::div[2]",
        "xpath=ancestor::div[1]",
    ):
        try:
            container = button.locator(xpath)
            if container.count() > 0:
                return container.first
        except Exception:
            continue
    return None


def _extract_name_title(button, page=None) -> tuple[str, str]:
    # FIX: advance count_ so it cycles 1 → 2 → … → 20 → 1 → …
    current_count = _next_count()

    container = _closest_card_container(button)
    try:
        aria_label = button.get_attribute("aria-label") or ""
    except Exception:
        aria_label = ""
    name_from_label = _name_from_aria_label(aria_label)

    if container is not None:
        title_from_xpath = ""
        try:
            # ── 1. Try the exact absolute structure LinkedIn uses for the title ──
            # Full path: …/div[2]/div/div[1]/a/div/div[1]/div/div[2]/p/span
            # We walk it as a relative path from ANY ancestor in the container.
            absolute_candidates = [
                # Exact relative path observed in production
                container.locator(f"xpath=.//div/div[{current_count}]/a/div/div[1]/div/div[2]/p/span"),
                container.locator(f"xpath=.//div[2]/div/div[{current_count}]/a/div/div[1]/div/div[2]/p/span"),
                container.locator(f"xpath=.//div/div[2]/div/div[{current_count}]/a/div/div[1]/div/div[2]/p/span"),
                # One level shallower (container IS the outer div[2])
                container.locator(f"xpath=.//div/div[{current_count}]/a/div/div[1]/div/div[2]/p/span"),
                # Previous fallbacks kept as lower priority
                container.locator("xpath=.//a/div/div[1]/div/div[2]/p/span"),
                container.locator("xpath=.//div/a/div/div[1]/div/div[2]/p/span"),
                container.locator("xpath=.//a//div/div[2]/p/span"),
                container.locator("xpath=.//a//p/span"),
                container.locator("xpath=.//p/span"),
                container.locator("xpath=.//span[contains(@class,'t-black--light')]"),
                container.locator("xpath=.//span[contains(@class,'t-normal')]"),
            ]

            # ── 2. Also try the absolute page-level XPath if page was passed in ──
            if page is not None:
                try:
                    abs_loc = page.locator(
                        f"xpath=//*[@id='workspace']//div/div[{current_count}]/a/div/div[1]/div/div[2]/p/span"
                    )
                    if abs_loc.count() > 0:
                        absolute_candidates.insert(0, abs_loc)
                except Exception:
                    pass

            title_locators = absolute_candidates
            for candidates in title_locators:
                for i in range(min(candidates.count(), 10)):
                    t = _clean_text(candidates.nth(i).inner_text())
                    if not t:
                        continue
                    if IGNORE_CARD_LINE_RE.fullmatch(t):
                        continue
                    if ACCEPT_RE.match(t) or CONNECT_RE.match(t):
                        continue
                    if name_from_label and t.casefold() == name_from_label.casefold():
                        continue
                    title_from_xpath = t
                    break
                if title_from_xpath:
                    break
        except Exception:
            title_from_xpath = ""

        try:
            text = container.inner_text()
        except Exception:
            text = ""

        if text:
            lines: list[str] = []
            for raw in text.splitlines():
                line = _clean_text(raw)
                if not line:
                    continue
                if IGNORE_CARD_LINE_RE.fullmatch(line):
                    continue
                if ACCEPT_RE.match(line) or CONNECT_RE.match(line):
                    continue
                lines.append(line)

            seen: set[str] = set()
            unique: list[str] = []
            for line in lines:
                key = line.casefold()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(line)

            name = unique[0] if unique else ""
            if name and (ACCEPT_RE.match(name) or CONNECT_RE.match(name)) and name_from_label:
                name = name_from_label

            title = title_from_xpath
            for line in unique[1:]:
                if title:
                    break
                if re.search(r"\bmutual\b", line, flags=re.IGNORECASE):
                    continue
                if re.search(r"\bconnections?\b", line, flags=re.IGNORECASE) and re.search(r"\b\d+\b", line):
                    continue
                if re.search(r"\bfollowers?\b", line, flags=re.IGNORECASE):
                    continue
                if re.search(r"\bago\b", line, flags=re.IGNORECASE):
                    continue
                title = line
                break

            if not name and name_from_label:
                name = name_from_label

            return name, title

    return name_from_label, ""


def _build_csv_row(button) -> dict[str, str]:
    name, title = _extract_name_title(button)
    clicked_at = datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")
    return {"name": name, "title": title, "time": clicked_at}


# ── title keyword filter ────────────────────────────────────────────────────

def _title_matches_keywords(title: str, keywords: list[str]) -> bool:
    """Return True if *any* keyword is found (case-insensitive) in the title.
    If keywords list is empty → always match (no filter active)."""
    if not keywords:
        return True
    title_lower = title.casefold()
    return any(kw in title_lower for kw in keywords)


# ── coloured print helpers ──────────────────────────────────────────────────

def _badge(label: str, bg: str) -> str:
    """Return a coloured pill badge string."""
    return f"{_C.BOLD}{bg}{_C.BLACK} {label} {_C.RESET}"


def _print_action(action: str, bg: str, row: dict[str, str]) -> None:
    name  = row.get("name")  or "(unknown)"
    title = row.get("title") or "(no title)"
    ts    = row.get("time")  or ""

    # Re-format the ISO timestamp stored in the CSV to the pretty format
    try:
        dt = datetime.fromisoformat(ts)
        ts = _fmt_time(dt)
    except Exception:
        pass  # keep raw if parsing fails

    badge     = _badge(action, bg)
    name_str  = f"{_C.BOLD}{_C.WHITE}{name}{_C.RESET}"
    title_str = f"{_C.YELLOW}{title}{_C.RESET}"
    time_str  = f"{_C.DIM}{_C.CYAN}{ts}{_C.RESET}"
    sep       = f"{_C.DIM} │ {_C.RESET}"

    print(f"{badge}  {name_str}{sep}{title_str}{sep}{time_str}", flush=True)


def _click_first_with_row(locator, *, timeout_ms: int = 5000, debug_label: str = "", page=None) -> dict[str, str] | None:
    count = locator.count()
    failures_printed = 0
    for i in range(count):
        candidate = locator.nth(i)
        name, title = _extract_name_title(candidate, page=page)
        try:
            candidate.click(timeout=timeout_ms)
            clicked_at = datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")
            return {"name": name, "title": title, "time": clicked_at}
        except Exception as e:
            if os.getenv("PW_DEBUG", "0") == "1" and failures_printed < 2:
                print(f"[debug] {debug_label} click failed: {type(e).__name__}: {e}")
                failures_printed += 1
            continue
    return None


def _click_first_with_row_filtered(
    locator,
    *,
    keywords: list[str],
    timeout_ms: int = 5000,
    debug_label: str = "",
    page=None,
) -> dict[str, str] | None:
    """Like _click_first_with_row but skips candidates whose title does NOT
    contain any of the required keywords.  Returns the row dict on success,
    None when no matching candidate could be clicked, or the special string
    'SKIPPED' stored in row['_skipped'] when candidates existed but were all
    filtered out by keyword.
    """
    count = locator.count()
    failures_printed = 0
    had_keyword_skip = False

    for i in range(count):
        candidate = locator.nth(i)
        name, title = _extract_name_title(candidate, page=page)

        # ── keyword gate: skip this person if title doesn't match ──
        if keywords and not _title_matches_keywords(title, keywords):
            had_keyword_skip = True
            _print_action(
                " SKIP  ",
                _C.BG_YELLOW,
                {"name": name, "title": title or "(no title)", "time": ""},
            )
            continue

        try:
            candidate.click(timeout=timeout_ms)
            clicked_at = datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")
            return {"name": name, "title": title, "time": clicked_at}
        except Exception as e:
            if os.getenv("PW_DEBUG", "0") == "1" and failures_printed < 2:
                print(f"[debug] {debug_label} click failed: {type(e).__name__}: {e}")
                failures_printed += 1
            continue

    # Return a sentinel so the caller knows we had candidates but skipped them
    if had_keyword_skip:
        return {"_skipped": "1"}
    return None


def _click_first(locator, *, timeout_ms: int = 5000, debug_label: str = "") -> bool:
    count = locator.count()
    failures_printed = 0
    for i in range(count):
        candidate = locator.nth(i)
        try:
            candidate.click(timeout=timeout_ms)
            return True
        except Exception as e:
            if os.getenv("PW_DEBUG", "0") == "1" and failures_printed < 2:
                print(f"[debug] {debug_label} click failed: {type(e).__name__}: {e}")
                failures_printed += 1
            continue
    return False


def _maybe_handle_connect_modal(page) -> None:
    if _click_first(
        page.get_by_role("button", name=re.compile(r"^Send(\s|$)", re.IGNORECASE)),
        debug_label="modal:send",
    ):
        page.wait_for_timeout(200)
        return

    if _click_first(
        page.get_by_role("button", name=re.compile(r"^Send now(\s|$)", re.IGNORECASE)),
        debug_label="modal:send-now",
    ):
        page.wait_for_timeout(200)
        return

    if _click_first(
        page.get_by_role("button", name=re.compile(r"^Done(\s|$)", re.IGNORECASE)),
        debug_label="modal:done",
    ):
        page.wait_for_timeout(200)
        return


def click_all_accept_and_connect(
    page,
    *,
    connect_refresh_every: int = 20,
    max_total_clicks: int = 2000,
    max_connect_clicks: int | None = None,
    title_keywords: list[str] | None = None,
) -> tuple[int, int]:
    accept_clicked = 0
    connect_clicked = 0
    connect_since_refresh = 0
    total_clicks = 0
    scroll_tries = 0
    max_scroll_tries = 25
    keywords = title_keywords or []

    while total_clicks < max_total_clicks:
        clicked_any = False

        # ── Accept (no keyword filter — always accept) ──────────────────────
        accept_by_role = page.get_by_role("button", name=ACCEPT_RE)
        accept_by_text = page.locator("button").filter(has_text=ACCEPT_RE)
        row = _click_first_with_row(accept_by_role, debug_label="accept(role)", page=page)
        if row is None:
            row = _click_first_with_row(accept_by_text, debug_label="accept(text)", page=page)
        if row is not None:
            _append_csv_row(ACCEPT_CSV_PATH, row)
            _print_action("ACCEPT ", _C.BG_GREEN, row)
            accept_clicked += 1
            total_clicks += 1
            clicked_any = True
            scroll_tries = 0
            page.wait_for_timeout(300)
            continue

        if max_connect_clicks is not None and connect_clicked >= max_connect_clicks:
            break

        # ── Connect (with keyword filter) ───────────────────────────────────
        connect_by_role = page.get_by_role("button", name=CONNECT_RE)
        connect_by_text = page.locator("button").filter(has_text=CONNECT_TEXT_RE)

        row = _click_first_with_row_filtered(
            connect_by_role,
            keywords=keywords,
            debug_label="connect(role)",
            page=page,
        )
        if row is None or row.get("_skipped"):
            row2 = _click_first_with_row_filtered(
                connect_by_text,
                keywords=keywords,
                debug_label="connect(text)",
                page=page,
            )
            # Use row2 if it's an actual click; keep skip sentinel otherwise
            if row2 is not None and not row2.get("_skipped"):
                row = row2
            elif row2 is not None:
                # both locators returned skip sentinels
                row = row2

        # If row is the skip sentinel, all visible connect buttons were
        # filtered out → scroll to find new ones
        if row is not None and row.get("_skipped"):
            if scroll_tries < max_scroll_tries:
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(600)
                scroll_tries += 1
                continue
            break

        if row is not None:
            _append_csv_row(CONNECT_CSV_PATH, row)
            _print_action("CONNECT", _C.BG_CYAN, row)
            _maybe_handle_connect_modal(page)
            connect_clicked += 1
            connect_since_refresh += 1
            total_clicks += 1
            clicked_any = True
            scroll_tries = 0
            page.wait_for_timeout(300)

            if connect_refresh_every > 0 and connect_since_refresh >= connect_refresh_every:
                page.reload(wait_until="domcontentloaded")
                connect_since_refresh = 0
                scroll_tries = 0
                page.wait_for_timeout(800)
            continue

        if not clicked_any:
            if scroll_tries < max_scroll_tries:
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(600)
                scroll_tries += 1
                continue
            break

    return accept_clicked, connect_clicked


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page()
    page.goto("https://www.linkedin.com/login/en-us/?trk=guest_homepage-basic_nav-header-signin")

    email = os.getenv("LINKEDIN_EMAIL") or input("LinkedIn email: ").strip()
    password = os.getenv("LINKEDIN_PASSWORD") or getpass.getpass("LinkedIn password: ")

    page.get_by_role("textbox", name="Email or phone").fill(email)
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("textbox", name="Password").press("Enter")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    if "checkpoint/challenge" in page.url:
        verification_method = page.get_by_role("heading", name=re.compile(r"^How do you want to receive your verification code\?$")).text_content()
        print(f"Verification method: {verification_method}")
        code = input("Enter the verification code you received: ")
        page.get_by_role("spinbutton", name="Verification code").fill(code)
        page.get_by_role("button", name="Submit pin").click()
        page.wait_for_load_state("domcontentloaded")

    page.wait_for_timeout(1000)
    page.goto("https://www.linkedin.com/mynetwork/invitation-manager/received/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    if "/login" in page.url:
        print(f"{_C.BOLD}{_C.RED}✖  Redirected to login — no actions taken.{_C.RESET}")
        browser.close()
        return

    if os.getenv("PW_DEBUG", "0") == "1":
        print(f"Current URL: {page.url}")
        print(f"Accept(role) candidates: {page.get_by_role('button', name=ACCEPT_RE).count()}")
        print(f"Connect(role) candidates: {page.get_by_role('button', name=CONNECT_RE).count()}")
        print(f"Accept(text) candidates: {page.locator('button').filter(has_text=ACCEPT_RE).count()}")
        print(f"Connect(text) candidates: {page.locator('button').filter(has_text=CONNECT_TEXT_RE).count()}")

    _ensure_csv_file(ACCEPT_CSV_PATH)
    _ensure_csv_file(CONNECT_CSV_PATH)

    # ── Connect limit ───────────────────────────────────────────────────────
    connect_limit_raw = (os.getenv("CONNECT_LIMIT") or "").strip()
    if not connect_limit_raw:
        connect_limit_raw = input("How many Connect clicks do you need? (Enter = no limit): ").strip()

    max_connect_clicks: int | None
    if not connect_limit_raw:
        max_connect_clicks = None
    else:
        try:
            max_connect_clicks = int(connect_limit_raw)
            if max_connect_clicks < 0:
                print(f"{_C.YELLOW}Connect clicks cannot be negative; running with no limit.{_C.RESET}")
                max_connect_clicks = None
        except ValueError:
            print(f"{_C.YELLOW}Invalid number for connect limit; running with no limit.{_C.RESET}")
            max_connect_clicks = None

    # ── Title keyword filter ────────────────────────────────────────────────
    keyword_raw = (os.getenv("TITLE_KEYWORD") or "").strip()
    if not keyword_raw:
        keyword_raw = input(
            "Title keyword filter — only Connect when title contains this "
            "(comma-separated, Enter = no filter): "
        ).strip()

    title_keywords: list[str] = []
    if keyword_raw:
        # Split by comma, strip whitespace, lowercase for case-insensitive match
        title_keywords = [kw.strip().casefold() for kw in keyword_raw.split(",") if kw.strip()]
        if title_keywords:
            kw_display = ", ".join(f'"{kw}"' for kw in title_keywords)
            print(
                f"{_C.BOLD}{_C.MAGENTA}⚙  Title keyword filter active: "
                f"{kw_display}{_C.RESET}"
            )
            print(
                f"{_C.DIM}   Only people whose title contains at least one "
                f"keyword will be connected.{_C.RESET}"
            )

    max_total_clicks = 2000
    if max_connect_clicks is not None:
        max_total_clicks = max(2000, max_connect_clicks + 200)

    # ── header ──────────────────────────────────────────────────────────────
    print(f"\n{_C.BOLD}{_C.CYAN}{'─' * 64}{_C.RESET}")
    print(f"  {_C.BOLD}{_C.WHITE}Starting LinkedIn automation …{_C.RESET}")
    if title_keywords:
        kw_display = ", ".join(title_keywords)
        print(f"  {_C.DIM}Filter: title must contain → {kw_display}{_C.RESET}")
    print(f"{_C.BOLD}{_C.CYAN}{'─' * 64}{_C.RESET}\n")

    accept_count, connect_count = click_all_accept_and_connect(
        page,
        connect_refresh_every=20,
        max_total_clicks=max_total_clicks,
        max_connect_clicks=max_connect_clicks,
        title_keywords=title_keywords,
    )

    # ── summary ─────────────────────────────────────────────────────────────
    print(f"\n{_C.BOLD}{_C.CYAN}{'─' * 64}{_C.RESET}")
    print(f"  {_C.BOLD}{'Action':<14}{_C.RESET}  {'Count':>6}   {'CSV file'}")
    print(f"  {_C.DIM}{'─' * 60}{_C.RESET}")
    print(f"  {_badge('ACCEPT ', _C.BG_GREEN)}  {_C.GREEN}{accept_count:>6}{_C.RESET}   {_C.DIM}{ACCEPT_CSV_PATH.name}{_C.RESET}")
    print(f"  {_badge('CONNECT', _C.BG_CYAN)}  {_C.CYAN}{connect_count:>6}{_C.RESET}   {_C.DIM}{CONNECT_CSV_PATH.name}{_C.RESET}")
    if title_keywords:
        kw_display = ", ".join(title_keywords)
        print(f"  {_C.DIM}Filter was: {kw_display}{_C.RESET}")
    print(f"{_C.BOLD}{_C.CYAN}{'─' * 64}{_C.RESET}\n")

    if accept_count == 0 and connect_count == 0 and os.getenv("PW_SCREENSHOT_ON_ZERO", "0") == "1":
        page.screenshot(path="debug_last_page.png", full_page=True)
        print(f"{_C.DIM}Saved screenshot: debug_last_page.png{_C.RESET}")

    time.sleep(5)
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
