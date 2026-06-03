# LinkedIn Auto Connect

Automate LinkedIn connection requests using Playwright and Python.

This tool logs into LinkedIn, navigates through search results, automatically sends connection requests, and stores processed profiles in CSV files to avoid duplicates.

> ⚠️ Disclaimer: This project is for educational purposes only. Using automation on LinkedIn may violate LinkedIn's Terms of Service. Use at your own risk.

---

## Features

* Secure LinkedIn login
* Automated connection requests
* CSV tracking of processed profiles
* Colored terminal output
* Configurable delays to mimic human behavior
* Pagination support
* Duplicate prevention
* Detailed execution logs

---

## Requirements

* Python 3.10+
* Google Chrome
* Playwright

---

## Installation

Clone the repository:

```bash
git clone https://github.com/wajih-ba/linkedin-auto-connect.git
cd linkedin-auto-connect
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install Playwright browsers:

```bash
playwright install
```

---

## Configuration

You can provide your LinkedIn credentials using environment variables.

### Windows

```cmd
set LINKEDIN_EMAIL=your_email@example.com
set LINKEDIN_PASSWORD=your_password
```

### Linux / macOS

```bash
export LINKEDIN_EMAIL="your_email@example.com"
export LINKEDIN_PASSWORD="your_password"
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
│   ├── connected_profiles.csv
│   └── processed_profiles.csv
└── logs/
    └── logs.csv
```

---

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
