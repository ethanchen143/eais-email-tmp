import os 
import requests
from dotenv import load_dotenv

# load_dotenv()
# INS_API_KEY = os.environ.get("INSTANTLY_API_KEY")
# url = "https://api.instantly.ai/api/v2/emails"
# query = {
#   "limit": "1",
#   "campaign_id": "c8262413-40fc-4916-85d9-84fb7cb63692",
#   "is_unread": "true",
#   "email_type": "received"
# }
# headers = {
#     'Authorization': f'Bearer {INS_API_KEY}',
# }
# response = requests.get(url, headers=headers, params=query)
# print(response.json())

from playwright.sync_api import sync_playwright

def scrape_page(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        content = page.content()
        browser.close()
        return content

print(scrape_page('https://www.converse.com/shop/p/converse-x-topo-chico-chuck-taylor-all-star-unisex-mid-shoe/A10455C.html'))