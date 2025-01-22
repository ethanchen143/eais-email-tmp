import json
import requests
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from email_writer import EmailWriter
import pandas as pd
import random
import string
from typing import List
import os
from add_campaign import create_campaign
from start_campaign import start_campaign
from dotenv import load_dotenv

VERSION = "1.0.0"

# gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 api:app

app = FastAPI()
email_writer_module = EmailWriter()


load_dotenv()
INS_API_KEY = os.environ.get("INSTANTLY_API_KEY")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # List the origins that should be allowed, or use ["*"] for all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

def load_campaigns():
    with open("campaigns.json", "r") as file:
        return json.load(file)

def save_campaigns(campaigns):
    with open("campaigns.json", "w") as file:
        json.dump(campaigns, file, indent=4)

def get_campaign_list(api_key):
    url = (
      f"https://api.instantly.ai/api/v1/campaign/list?"
      f"api_key={api_key}"
    )
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers)
    return response.json()

@app.get("/")
async def root():
    return {"Version": VERSION}

@app.post("/add_campaign/")
async def add_campaign(
    name: str = Form(...),
    initial_email_template: str = Form(""),  
    leads_file_path: str = Form("")
):
    # Generate a random suffix to avoid duplicate names
    random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
    unique_name = f"{name}_{random_suffix}"  # Append random suffix to the name
    # Get initial campaign IDs
    initial_campaign_ids = {campaign["id"] for campaign in get_campaign_list(INS_API_KEY)}
    # Create a new campaign
    create_campaign(unique_name)
    # Get final campaign IDs
    final_campaign_ids = {campaign["id"] for campaign in get_campaign_list(INS_API_KEY)}
    # Determine the new campaign ID
    new_campaign_ids = final_campaign_ids - initial_campaign_ids
    if new_campaign_ids:
        new_campaign_id = new_campaign_ids.pop()
        # Prepare campaign data
        campaign_data = {
            "campaign_name": unique_name,
            "campaign_id": new_campaign_id,
            "email_template": initial_email_template,
            "leads_file_path": leads_file_path,
            "intents": [],  
            "responses": [], 
            "status": "setup", # NEXT STAGE IS emailready, emailsent
            "generated_email_path": ""
        }
        # Write to JSON file
        try:
            with open("campaigns.json", "r") as file:
                if file.read().strip() == "":
                    existing_data = []
                else:
                    file.seek(0)
                    existing_data = json.load(file)
        except FileNotFoundError:
            existing_data = []
        existing_data.append(campaign_data)
        with open("campaigns.json", "w") as file:
            json.dump(existing_data, file, indent=4)
        return {"new_campaign_id": new_campaign_id, "status": "Campaign created successfully", "campaign": campaign_data}
    else:
        return {"status": "Failed to create new campaign", "name": unique_name}
            
def fetch_sending_accounts(api_key):
    url = f"https://api.instantly.ai/api/v1/account/list?api_key={api_key}&limit=25&skip=0"
    headers = {'Content-Type': 'application/json'}
    payload = {}
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        accounts = response.json().get("accounts", [])
        return accounts
    else:
        raise Exception(f"Failed to fetch accounts: {response.status_code} - {response.text}")

def add_accounts_to_campaign(api_key, campaign_id, accounts):
    url = "https://api.instantly.ai/api/v1/campaign/add/account"
    headers = {'Content-Type': 'application/json'}
    for account in accounts:
        payload = json.dumps({
            "api_key": api_key,
            "campaign_id": campaign_id,
            "email": account["email"]
        })
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            print(f"Successfully added account {account['email']} to campaign.")
        else:
            print(f"Failed to add account {account['email']} - {response.status_code} - {response.text}")

@app.post("/generate_emails/")
async def generate_emails(campaign_id: str = Form(...),):
    campaigns = load_campaigns()
    # Check if the campaign exists
    campaign_data = next((campaign for campaign in campaigns if campaign["campaign_id"] == campaign_id), None)

    if campaign_data:
        campaign_name = campaign_data["campaign_name"]
        campaign_id = campaign_data["campaign_id"]
        email_template = campaign_data["email_template"]
        leads_file_path = campaign_data["leads_file_path"]
        generated_email_path = email_writer_module.generate_email(leads_file_path, campaign_id, email_template)
        campaign_data["generated_email_path"] = generated_email_path
        campaign_data["status"] = "emailready"

        save_campaigns(campaigns)
        return {"status": True}
    else:
        return {"status": "Failed to generate emails"}

import os

@app.get("/campaign/get_emails/")
def get_emails(campaign_id: str):
    # Locate the generated emails file
    generated_email_path = f"emails/generated_emails_{campaign_id}.csv"
    if not os.path.exists(generated_email_path):
        raise HTTPException(status_code=404, detail="Generated email file not found.")

    # Read and return the emails as JSON
    df_emails = pd.read_csv(generated_email_path)
    return {"emails": df_emails.to_dict(orient="records")}

@app.post("/campaign/update_emails/")
def update_emails(campaign_id: str, emails: list[dict]):
    # Locate the generated emails file
    generated_email_path = f"emails/generated_emails_{campaign_id}.csv"
    if not os.path.exists(generated_email_path):
        raise HTTPException(status_code=404, detail="Generated email file not found.")

    # Convert the received JSON data back to a DataFrame
    df_updated = pd.DataFrame(emails)

    # Overwrite the existing CSV file with updated data
    try:
        df_updated.to_csv(generated_email_path, index=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save updates: {str(e)}")

    return {"status": "Success", "message": "Emails updated successfully."}

def add_leads_to_campaign(api_key, campaign_id, leads_file_path, batch_size=500):
    # Load leads from CSV
    df = pd.read_csv(leads_file_path)
    df.fillna("", inplace=True)

    # Map leads to the API format
    def map_lead(lead):
        full_name = lead.get("full_name", "").split(" ", 1)
        return {
            "email": lead.get("email", ""),
            "custom_variables": {
                "generated_email":lead.get("email_pitch",""),
            }
        }
    
    leads = [map_lead(lead) for lead in df.to_dict(orient="records")]

    url = "https://api.instantly.ai/api/v1/lead/add"
    headers = {'Content-Type': 'application/json'}
    total_leads = len(leads)
    total_batches = (total_leads // batch_size) + (1 if total_leads % batch_size != 0 else 0)
    for i in range(total_batches):
        batch_start = i * batch_size
        batch_end = batch_start + batch_size
        leads_batch = leads[batch_start:batch_end]
        payload = {
            "api_key": api_key,
            "campaign_id": campaign_id,
            "skip_if_in_workspace": False,
            "skip_if_in_campaign": True,
            "leads": leads_batch
        }
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        # Log result and handle response
        if response.status_code == 200:
            print(f"Batch {i+1}/{total_batches} added successfully.")
        else:
            print(f"Error with Batch {i+1}: {response.status_code} - {response.text}")

@app.post("/send_emails/")
async def send_emails(campaign_id: str = Form(...)):
    campaigns = load_campaigns()
    campaign_data = next((campaign for campaign in campaigns if campaign["campaign_id"] == campaign_id), None)
    if campaign_data:
        generated_email_path = campaign_data["generated_email_path"]
        accounts = fetch_sending_accounts(INS_API_KEY)
        add_accounts_to_campaign(INS_API_KEY,campaign_id,accounts)
        add_leads_to_campaign(INS_API_KEY,campaign_id,generated_email_path)
        start_campaign(campaign_id)
        campaign_data["status"] = "emailsent"
        save_campaigns(campaigns)
        return {"status": True}
    else:
        return {"status": "Failed to send emails"}
    
@app.post("/set_auto_reply/")
async def set_auto_reply(campaign_id: str = Form(...),    
                          intents: List[str] = Form([]),  
                          responses: List[str] = Form([]) ):
    return{}

@app.post("/stop_auto_reply/")
async def set_auto_reply(campaign_id: str = Form(...),    
                          intents: List[str] = Form([]),  
                          responses: List[str] = Form([]) ):
    return{}

# @app.post("/send_initial_emails/")
# async def send_initial_emails(cm_name: str = Form(...)):
    
#     campaign_list = get_campaign_list(INS_API_KEY)
#     campaign_id = get_campaign_id(campaign_list, cm_name)
    
#     campaign = redis_db.read(campaign_id)
#     if campaign: 
#         lead_list = []
#         for prepared_email in campaign:
#             email = list(prepared_email.keys())[0]
#             user_data= {
#                 "email": email,
#                 "first_name": prepared_email[email]['first_name'],
#                 "custom_variables": {
#                     "Profile Link": prepared_email[email]['profile_link'],
#                     "Username": prepared_email[email]['username'],
#                     "Followers Count": prepared_email[email]['followers_count'],
#                     "Full email":prepared_email[email]['full_email']
#             }
#             }
#             lead_list.append(user_data)
#         add_leads_to_campaign(INS_API_KEY, campaign_id, lead_list)
#         return {"status": True}

# @app.post("/receive_any_data/")
# async def receive_any_data(request: Request):
#     data = await request.json()
#     if data["event_type"] == "reply_received" and data["is_first"]:
#         campaign = redis_db.read(data["campaign_id"])
#         if campaign:
#             sent_email_info = email_exists_in_json(campaign, data["lead_email"], data["campaign_id"])
#             if sent_email_info:
#                 message = extract_most_recent_message(data['reply_html'])
#                 if message:
#                     respond_to_reply(data["lead_email"], message, data['email_account'], data['reply_subject'], data["campaign_id"])
            
#     return {"received_data": data}


# def get_email_reply_uuid(api_key, campaign_id, email_id):
#     url = (
#         f"https://api.instantly.ai/api/v1/unibox/emails?"
#         f"api_key={api_key}&preview_only=true&campaign_id={campaign_id}"
#         f"&email_type=received&lead={email_id}&latest_of_thread=true"
#     )

#     headers = {
#         'Content-Type': 'application/json'
#     }
    
#     response = requests.get(url, headers=headers)
    
#     return json.loads(response.text)['data'][0]['id']

# def send_email_reply(api_key, reply_to_uuid, subject, from_email, to_email, body):
#     url = f"https://api.instantly.ai/api/v1/unibox/emails/reply?api_key={api_key}"
    
#     payload = json.dumps({
#         "reply_to_uuid": reply_to_uuid,
#         "subject": subject,
#         "from": from_email,
#         "to": to_email,
#         "body": body,
#     })
    
#     headers = {
#         'Content-Type': 'application/json'
#     }
    
#     response = requests.post(url, headers=headers, data=payload)
    
#     return response.text

# def get_reply_uuid_and_respoond(subject, from_email, to_email, body, campaign_id):
#     reply_uuid = get_email_reply_uuid(INS_API_KEY, campaign_id, to_email)
#     send_email_reply(INS_API_KEY, reply_uuid, subject, from_email, to_email, body)

# def extract_most_recent_message(html_content):
#     soup = BeautifulSoup(html_content, 'html.parser')
#     # Find the first 'div' with dir='ltr' that is not inside a 'gmail_quote' div
#     recent_message = None
#     for div in soup.find_all('div', dir='ltr'):
#         if 'gmail_quote' not in div.get('class', []):
#             recent_message = div
#             break

#     # Extract the text from the found div
#     if recent_message:
#         recent_message_text = recent_message.get_text(strip=True)
#         return recent_message_text
#     else:
#         return None

# def email_exists_in_json(sent_emails, email, campaign_id):
#     for item in sent_emails:
#         if email in item:
#             return True
#     return False

# def respond_to_reply(lead_email, message, sent_via, reply_subject, campaign_id):
#     response_to_reply = email_writer_module.respond_to_reply(lead_email, campaign_id, message)
#     if response_to_reply:
#         get_reply_uuid_and_respoond(reply_subject, sent_via, lead_email, response_to_reply, campaign_id)