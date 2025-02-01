import json
import requests
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from email_writer import EmailWriter
import pandas as pd
import random
import string
from typing import List
import os
from dotenv import load_dotenv
import aiofiles
load_dotenv()

VERSION = "1.0.0"

app = FastAPI()
email_writer_module = EmailWriter()


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

def fetch_sending_accounts():
    url = f"https://api.instantly.ai/api/v2/accounts?limit=10&status=1"
    headers = {
        'Authorization': f'Bearer {INS_API_KEY}',
    }
    response = requests.get(url, headers=headers)
    return response.json()

# create and set up campaign
def create_campaign(campaign_name, email_title):
    url = "https://api.instantly.ai/api/v2/campaigns"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {INS_API_KEY}',
    }
    # get all email accounts
    email_accounts = [item['email'] for item in fetch_sending_accounts()['items']]
    data = {
        "name": campaign_name,
        'sequences': [{'steps': [{'type': 'email', 'delay': 2, 'variants': [{'subject': f'{email_title}', 'body': '{{personalization}}\n\n{{sendingAccountFirstName}}'}]}]}],
        "email_list": email_accounts,
        "campaign_schedule": {
            "schedules": [
                {
                "name": "My Schedule",
                "timing": {
                    "from": "09:00",
                    "to": "21:00"
                },
                "days": {
                    0: True, 1: True, 2: True, 3: True, 4: True, 5: False, 6: False
                },
                "timezone": "America/Chicago",
                }
            ]
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()

@app.get("/")
async def root():
    return {"Version": VERSION}


""" add campaignn: create campaign, link the sending accounts to campaign, store campaign info """
@app.post("/add_campaign/")
async def add_campaign(
    name: str = Form(...),
    initial_email_template: str = Form(""),
    email_title: str = Form(""),
    file: UploadFile = File(...)
):
    # Generate a random suffix to avoid duplicate names
    random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
    unique_name = f"{name}_{random_suffix}"  # Append random suffix to the name

    if not email_title:
        email_title = "Hello {{firstName}}!"
    new_campaign_id = create_campaign(unique_name, email_title)['id']

    os.makedirs("leads", exist_ok=True)
    # Save uploaded file
    file_path = os.path.join("leads", f"{new_campaign_id}.csv")
    try:
        # Async write file
        async with aiofiles.open(file_path, "wb") as f:
            content = await file.read()
            await f.write(content)
    except Exception as e:
        return {"status": f"File upload failed: {str(e)}"}

    # Prepare campaign data
    campaign_data = {
        "campaign_name": unique_name,
        "campaign_id": new_campaign_id,
        "email_template": initial_email_template,
        "leads_file_path": file_path,
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

@app.get("/campaign/get_emails/{campaign_id}")
def get_emails(campaign_id: str):
    # Locate the generated emails file
    generated_email_path = f"emails/generated_emails_{campaign_id}.csv"
    if not os.path.exists(generated_email_path):
        raise HTTPException(status_code=404, detail="Generated email file not found.")

    # Read and return the emails as JSON
    df_emails = pd.read_csv(generated_email_path)
    return {"emails": df_emails.to_dict(orient="records")}

@app.post("/campaign/update_emails/{campaign_id}")
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

def start_campaign(id):
    url = f"https://api.instantly.ai/api/v2/campaigns/{id}/activate"
    headers = {
        'Authorization': f'Bearer {INS_API_KEY}',
    }
    response = requests.post(url, headers=headers)
    return response.json()

def add_leads_to_campaign(campaign_id):
    df = pd.read_csv(f'./emails/generated_emails_{campaign_id}.csv')
    url = "https://api.instantly.ai/api/v2/leads"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {INS_API_KEY}',
    }
    for idx,row in df.iterrows():
        data = {
            "campaign": campaign_id,
            "email": row['email'],
            "first_name": row['username'],
            "last_name": row['full_name'],
            "personalization": row['email_pitch']
        }
        response = requests.post(url,headers=headers,json=data)

""" add leads to campaign and start campaign. """
@app.post("/send_emails/")
async def send_emails(campaign_id: str = Form(...)):
    campaigns = load_campaigns()
    campaign_data = next((campaign for campaign in campaigns if campaign["campaign_id"] == campaign_id), None)
    if campaign_data:
        add_leads_to_campaign(campaign_id)
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