from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import sys
import os
from dotenv import load_dotenv

load_dotenv()
USERNAME = os.environ.get("INSTANTLY_USERNAME")
PASSWORD = os.environ.get("INSTANTLY_PASSWORD")
URL = "https://app.instantly.ai/"

def start_campaign(campaign_id):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Connect to Selenium container
    driver = webdriver.Remote(
        command_executor='http://selenium:4444/wd/hub',
        options=chrome_options
    )

    wait = WebDriverWait(driver, 10)

    try:
        # Open Instantly campaigns page
        driver.get("https://app.instantly.ai/")

        # Wait for login page and enter email
        email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))  # Replace "email" with the actual field name or ID if needed
        email_field.send_keys(USERNAME)

        # Enter password
        password_field = driver.find_element(By.NAME, "password")  # Replace "password" with the actual field name or ID if needed
        password_field.send_keys(PASSWORD)

        # Click the login button
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")  # Replace with the actual XPATH or CSS selector for the login button
        login_button.click()

        # Wait for the campaigns page to load
        time.sleep(2)
        driver.get(f"https://app.instantly.ai/app/campaign/{campaign_id}/sequences")
        time.sleep(1)

        try:
            confirm_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue')]") 
            confirm_button.click()
        except:
            pass

        subject_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Your subject']")))
        subject_field.clear()
        subject_field.send_keys("Campaign Subject")
        
        # Wait for the body field (contenteditable div)
        body_field = wait.until(EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true']")))

        # Clear the existing text (if necessary, you can select all and delete)
        action_chains = ActionChains(driver)
        action_chains.click(body_field).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.DELETE).perform()

        # Send new text to the contenteditable div
        body_field.send_keys("{{generated_email}} \n {{sendingAccountFirstName}}")

        save_button = driver.find_element(By.ID, "custom-save")
        save_button.click()

        # Locate the button using its text content
        resume_button = driver.find_element(By.XPATH, "//div[text()='Resume campaign']")

        # Click the button
        resume_button.click()

        time.sleep(2)

        print(f"Campaign '{campaign_id}' started successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    campaign_id = sys.argv[1]
    start_campaign(campaign_id)