# LinkedIn Auto Connect

Automate LinkedIn connection requests using Playwright and Python.

This tool logs into LinkedIn, navigates through search results, automatically sends connection requests, and stores processed profiles in CSV files.

## Features

* Secure LinkedIn login
* Automated connection requests
* CSV tracking of processed profiles
* Configurable delays to mimic human behavior
* Pagination support
* Duplicate prevention
* Detailed execution logs

---

## Requirements

* Python 3.10+
* Google Chrome
* Playwright


Install Playwright browsers:

```bash
playwright install
```

If credentials are not provided, the script will prompt for them at runtime.

---

## Usage

Run the script:

```bash
python main.py
```

The bot will:

1. Log into LinkedIn.
2. Open the configured search page.
3. Detect available profiles.
4. Send connection requests.
5. Save processed profiles to CSV.
6. Continue until all pages are processed.

---

## Output Files

| File                   | Description                     |
| ---------------------- | ------------------------------- |
| connected_profiles.csv | Successfully connected profiles |
| processed_profiles.csv | All processed profiles          |
| logs.csv               | Execution logs                  |

---

## Project Structure

```text
linkedin-auto-connect/
│
├── main.py
├── requirements.txt
├── README.md
├── data/
```

## Safety Recommendations

To reduce the risk of LinkedIn restrictions:

* Limit daily connection requests.
* Use random delays.
* Avoid running the bot continuously.
* Monitor account activity regularly.
* Respect LinkedIn usage policies.

---

## Technologies Used

* Python
* Playwright
* CSV
* Regular Expressions (Regex)
