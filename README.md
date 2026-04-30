# LinkedIn Auto Connect Bot

A Python automation script that leverages SeleniumBase to automatically send connection requests on LinkedIn. The bot extracts the name and title of the people it connects with and securely stores them into a local SQLite database (`users.db`) using Flask-SQLAlchemy.

## Features
- **Automated Connections**: Automatically clicks the "Connect" button on your network growth page.
- **Data Scraping**: Extracts the name and profile title for the users you connect with.
- **Database Storage**: Seamlessly saves extracted data into a local SQLite database.
- **Headless Mode**: Runs the browser session securely in the background.
- **Persistent Sessions**: Uses a local Chrome profile (`Chrome_profile` directory) so you only need to log in manually once. Fallbacks securely to a temporary profile if needed.

## Prerequisites
- Python 3.8 or higher.
- Google Chrome browser installed on your machine.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/wajih-ba/linkedin-auto-connect.git
   cd linkedin-auto-connect
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the script by typing:
```bash
python main.py
```

**Note**: The very first time you run the script, you will have up to 5 minutes to manually log into LinkedIn. The script waits until it detects a successful login redirect, at which point it begins the connection flow. Future runs will reuse your authenticated profile session.

## Database
The program creates a `users.db` SQLite database in the root folder automatically. The database structure contains:
- `id`: Internal ID.
- `name`: User's full name.
- `title`: User's profile title/headline.

## Disclaimer
This project is for educational and research purposes only. Automating LinkedIn actions is against their Terms of Service and could result in account restriction or bans. Use this tool entirely at your own risk.