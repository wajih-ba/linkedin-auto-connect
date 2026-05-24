import sys

from seleniumbase import Driver
import time
import os
import tempfile
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

def create_driver(headless=True):
    return Driver(uc=True, headless=headless)

def click_connect_button(driver,rep):
    rept = 20
    while rep != -20: 
        if rep < 20 :
            rept  = rep%20
            rep = 0
        for _ in range(1,rept+1):
            connect_xpath = f"//*[@id='workspace']/div/div/section/section/div/div[2]/div/div/div[2]/div/div[{_}]/a/div/div[2]/div/button"
            name_xpath = f"//*[@id='workspace']/div/div/section/section/div/div[2]/div/div/div[2]/div/div[{_}]/a/div/div[1]/div/div[1]/p/span/span[2]"
            title_xpath = f"//*[@id='workspace']/div/div/section/section/div/div[2]/div/div/div[2]/div/div[{_}]/a/div/div[1]/div/div[2]/p/span"
            try:
                connect_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, connect_xpath)))
                time.sleep(random.uniform(0.5,1))  # Small delay to ensure the button is fully interactable
                connect_button.click()
                name_element = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, name_xpath)))
                title_element = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, title_xpath)))

                import csv
                
                # Save to CSV file
                try:
                    # Check if user already exists in file
                    user_exists = False
                    try:
                        with open('users.csv', 'r', encoding='utf-8') as f:
                            existing_users = f.read()
                            if name_element.text in existing_users:
                                user_exists = True
                    except FileNotFoundError:
                        pass # File will be created

                    if not user_exists:
                        file_exists = os.path.isfile('users.csv')
                        with open('users.csv', 'a', encoding='utf-8', newline='') as f:
                            writer = csv.writer(f)
                            if not file_exists:
                                writer.writerow(['Name', 'Title', 'Timestamp']) # Write header if new file
                            writer.writerow([name_element.text, title_element.text, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                        print(f"\033[92m[+] Added:\033[0m {name_element.text} | \033[96m{title_element.text}\033[0m")
                    else:
                        print(f"\033[93m[-] User {name_element.text} already exists in file.\033[0m")
                except Exception as e:
                    print(f"\033[91m[!] Failed to write to file:\033[0m {e}")

            except Exception:
                try:
                    connect_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, connect_xpath)))
                    driver.execute_script("arguments[0].click();", connect_button)
                except Exception:
                    print(f"Failed to click connect button for index {_}")
        rep -=20
        driver.refresh()
def login (driver):
    email = input("Enter your LinkedIn email: ")
    password = input("Enter your LinkedIn password: ")    
    email_xpath = "//*[@id='username']"
    psw_xpath = "//*[@id='password']"
    login_button_xpath = "//*[@id='organic-div']/form/div[4]/button"

    try:
        WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, email_xpath))).send_keys(email)
        WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, psw_xpath))).send_keys(password)
        WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, login_button_xpath))).click()
    except Exception as exc:    
        try:
            login_button_xpath = "//*[@id='workspace']/div/div[2]/div/div[1]/div/div/div[2]/div/div/div/div[2]/div/div[3]/button"
            email_xpath = "//*[@id=':r3:']"
            psw_xpath = "//*[@id=':r4:']"
            WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, email_xpath))).send_keys(email)
            WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, psw_xpath))).send_keys(password)
            WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, login_button_xpath))).click()
        except Exception as exc:
                print(f"Error during login: {exc}")
                return False
    
    # Check if login was successful
    try:
        WebDriverWait(driver, 2).until(lambda d: "linkedin.com/feed" in d.current_url or "linkedin.com/mynetwork" in d.current_url or "linkedin.com/checkpoint" in d.current_url)
        if "checkpoint" in driver.current_url:
            driver.activate_cdp_mode(driver.current_url)
            time.sleep(29)
            print("Login requires additional verification (2FA or security check). Please complete it manually in the browser.")
            return False
        return True
    except Exception:
        print("Login failed - credentials may be incorrect or there's a login issue.")
        return False
def accept_button(driver):
    
    i=1
    while True:
        accept_xpath = f"//*[@id='workspace']/div/div/div[1]/section/div/div[2]/div/div/div[{i}]/div/div[1]/div/div/div[2]/div[2]/button"
        try:
            accept_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, accept_xpath)))
            time.sleep(random.uniform(0.5, 1))  # Small delay to ensure the button is fully interactable
            accept_button.click()
        except Exception:
            break
        i+=1

def main() :
    driver = create_driver()
    login_url = "https://www.linkedin.com/login/"
    driver.get(login_url)
    if not login(driver):
        print("Login unsuccessful. Exiting.")
        driver.quit()
        sys.exit(1)
    try:
        print("Login successful. Proceeding...")
        driver.get("https://www.linkedin.com/mynetwork/invitation-manager/")
        accept_button(driver)
        i=0
        repetation = int(input("Enter the number of times you want to click the connect button: "))
        
        click_connect_button(driver,repetation)
            
        print(f"Finished connection with :  {repetation}.")
            
    except Exception as exc:
        print(f"Timed out or error while locating page elements: {exc}")
if __name__ == "__main__":
    main()
