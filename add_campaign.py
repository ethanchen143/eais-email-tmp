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

def create_campaign(campaign_name):
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
        driver.get(URL)

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
        time.sleep(5)
        driver.get("https://app.instantly.ai/app/campaigns")
        time.sleep(1)

        # Click on "Add New Campaign" button
        add_campaign_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='Add new']")))
        add_campaign_button.click()

        # Wait for the campaign name input field to appear and enter the campaign name
        campaign_name_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Give your campaign a name']")))
        campaign_name_field.clear()
        campaign_name_field.send_keys(campaign_name)
        # # Confirm creation (adjust the locator to match the button or action)
        confirm_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue')]")  # Adjust the XPATH based on the button text
        confirm_button.click()

        print(f"Campaign '{campaign_name}' created successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    campaign_name = sys.argv[1]
    create_campaign(campaign_name)