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

# from api import extract_restaurant_labels
# extract_restaurant_labels("hello world")

import requests
RESTAURANT_API_URL = "http://localhost:3000"

url = RESTAURANT_API_URL + "/api/chubby/data"
payload = {
    "email": "ethanchen143@gmail.com",
    "location": "Mikiya Wagyu Shabu House Houston"
}

response = requests.post(url, json=payload)

print(response.status_code)
print(response.json())

# url = RESTAURANT_API_URL + "/api/chubby/data/e2e916f4-9711-403a-9802-40fb74483ab4/status"
# payload = {
#     "statusType": "interested",
#     "newStatus": "pending"
# }

# response = requests.put(url, json=payload)

# print(response.status_code)
# print(response.json())