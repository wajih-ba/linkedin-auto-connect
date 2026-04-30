from seleniumbase import Driver
import time
import os
import tempfile
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String

class Base(DeclarativeBase):
    pass

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# CREATE TABLE IN DB
class User(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(100))

with app.app_context():
    db.create_all()

def create_driver():
    user_data_dir = os.path.join(os.getcwd(), "Chrome_profile")
    try:
        return Driver(uc=True, user_data_dir=user_data_dir, headless=True)
    except Exception:
        # If the profile is locked/crashed, retry with a clean temporary profile.
        fallback_dir = tempfile.mkdtemp(prefix="linkedin_bot_")
        return Driver(uc=True, user_data_dir=fallback_dir , headless=True)

def click_connect_button(driver) -> None:
    for _ in range(1,9):
        connect_xpath = f"//*[@id='workspace']/div/div/div[2]/div/div/div/div/div[3]/section/div/div[2]/div[{_}]/div/div/div[1]/div/div[2]/button"
        name_xpath = f"//*[@id='workspace']/div/div/div[2]/div/div/div/div/div[3]/section/div/div[2]/div[{_}]/div/div/div[1]/a/div/div[2]/div[1]/p/span[2]"
        title_xpath = f"//*[@id='workspace']/div/div/div[2]/div/div/div/div/div[3]/section/div/div[2]/div[{_}]/div/div/div[1]/a/div/div[2]/div[2]/p"
        try:
            connect_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, connect_xpath)))
            time.sleep(random.uniform(1, 3))  # Small delay to ensure the button is fully interactable
            connect_button.click()
            name_element = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, name_xpath)))
            print(f"Name found for index {_}: {name_element.text}")
            title_element = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, title_xpath)))
            print(f"Title found for index {_}: {title_element.text}")
            
            with app.app_context():
                new_user = User(name=name_element.text, title=title_element.text)
                try:
                    db.session.add(new_user)
                    db.session.commit()
                    print(f"Added {name_element.text} to database.")
                except Exception as db_error:
                    db.session.rollback()
                    print(f"Failed to add to database (possibly duplicate): {db_error}")

        except Exception:
            try:
                connect_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, connect_xpath)))
                driver.execute_script("arguments[0].click();", connect_button)
            except Exception as e:
                print(f"Failed to click button for index {_}: {e}")
    driver.refresh()


def main() -> None:
    driver = create_driver()
    login_url = "https://www.linkedin.com/login/"

    try:
        driver.get(login_url)
        print("Waiting for the LinkedIn login to complete...")
        # Wait up to 5 minutes for the user to log in and get redirected
        WebDriverWait(driver, 300).until(
            lambda d: "linkedin.com/feed" in d.current_url or "linkedin.com/mynetwork" in d.current_url
        )
        
        driver.get("https://www.linkedin.com/mynetwork/grow/")
        for _ in range(1,3):
            click_connect_button(driver)
            
    except Exception as exc:
        print(f"Timed out or error while locating page elements: {exc}")
if __name__ == "__main__":
    main()
