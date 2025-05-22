import os 
import requests
from dotenv import load_dotenv
load_dotenv()
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

# url = RESTAURANT_API_URL + "/api/chubby/data"
# payload = {
#     "email": "ethanchen143@gmail.com",
#     "location": "Mikiya Wagyu Shabu House Houston"
# }

# response = requests.post(url, json=payload)

# print(response.status_code)
# print(response.json())

# url = RESTAURANT_API_URL + "/api/chubby/data/e2e916f4-9711-403a-9802-40fb74483ab4/status"
# payload = {
#     "statusType": "interested",
#     "newStatus": "pending"
# }

# response = requests.put(url, json=payload)

# print(response.status_code)
# print(response.json())


import requests

CAMPAIGN_ID = "a4682b71-34a6-4c82-bb4d-ed396b118e3e"

url = "https://api.instantly.ai/api/v2/emails"

#   "starting_after": "01968323-149b-785a-bcb8-bbe8806ff5b0",

query = {
  "limit": "100",
  "campaign_id": CAMPAIGN_ID,
  "email_type": "sent"
}

INS_API_KEY = os.environ.get("INSTANTLY_API_KEY")

headers = {
    'Authorization': f'Bearer {INS_API_KEY}',
    'Accept': 'application/json' # Good practice to include Accept header
}

response = requests.get(url, headers=headers, params=query)
print(response.status_code)

data = response.json()
import json

# Save the data to a file
with open("new_sent.json", "w") as f:
    json.dump(data, f, indent=2)