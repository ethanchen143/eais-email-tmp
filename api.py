import json
import requests
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from email_writer import EmailWriter, GptOperations
import pandas as pd
import random
import string
from typing import List
import os
import copy
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from constants import get_keywords_prompt
import aiofiles
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()
VERSION = "1.0.0"
app = FastAPI()
email_writer_module = EmailWriter()
gpt_ops_module = GptOperations()
INS_API_KEY = os.environ.get("INSTANTLY_API_KEY")

# MongoDB Connection
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE_NAME = os.getenv("MONGODB_DATABASE_NAME")
client = MongoClient(MONGODB_URI)
db = client[MONGODB_DATABASE_NAME]
campaigns_collection = db["campaigns"]
leads_collection = db["leads"]
generated_emails_collection = db["generated_emails"]

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # List the origins that should be allowed, or use ["*"] for all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


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

def scrape_page(url):
    url = url.strip('/')
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve {url}: {e}")
        return
    soup = BeautifulSoup(response.content, 'html.parser')
    page_text = soup.get_text(separator='\n').strip()
    page_text = page_text.replace('\n','').replace(' ','')
    return page_text

@app.get("/get_keywords")
async def get_keywords(
    product_url: str = Query(...),
    brand_url: str = Query(...)
):     
    
    print("API Key:", os.environ)
    product_page = scrape_page(product_url)
    brand_page = scrape_page(brand_url)
    get_keywords_prompt_for_ds = copy.deepcopy(get_keywords_prompt).format(
        brand = brand_page, product = product_page
    )
    print("get_keywords_prompt_for_ds:",get_keywords_prompt_for_ds)
    response, status = gpt_ops_module.call_gpt_openai_json(prompt=get_keywords_prompt_for_ds,model="gpt-4o-mini")
    print("response:",response)
    try:
        keywords = json.loads(response) if isinstance(response, str) else response
    except Exception as e:
        raise HTTPException(status_code=400, detail="Deepseek returned invalid JSON")
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        raise HTTPException(status_code=400, detail="Response is not a list of strings")
    
    return {"keywords": keywords}

@app.get("/generate_template")
async def generate_template(
    product_url: str = Query(...),
    brand_url: str = Query(...)
):  
    product_page = scrape_page(product_url)
    brand_page = scrape_page(brand_url)
    get_keywords_prompt_for_ds = copy.deepcopy(generate_template_prompt).format(
        brand = brand_page, product = product_page
    )
    response, status = gpt_ops_module.call_gpt_openai_json(prompt=get_keywords_prompt_for_ds,model="gpt-4o-mini")
    try:
        keywords = json.loads(response) if isinstance(response, str) else response
    except Exception as e:
        raise HTTPException(status_code=400, detail="Deepseek returned invalid JSON")
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        raise HTTPException(status_code=400, detail="Response is not a list of strings")
    
    return {"keywords": keywords}

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


    try:

            content = await file.read()
            data = pd.read_csv(pd.io.common.BytesIO(content))  # Read CSV as Pandas DataFrame


            # Convert DataFrame to structured format
            lead_data = []
            for _, row in data.iterrows():
                lead_data.append({
                    "username": row["username"],
                    "name": row["full_name"],
                    "bio": row["bio"],
                    "desc": row["video_desc"],
                    "email": row["email"],
                })

            # Insert leads under campaign_id
            leads_collection.insert_one({
                "campaign_id": new_campaign_id,
                "data": lead_data
            })
        
            #await f.write(content)
    except Exception as e:
        return {"status": f"File upload failed: {str(e)}"}

    # Prepare campaign data
    campaign_data = {
        "campaign_name": unique_name,
        "campaign_id": new_campaign_id,
        "email_template": initial_email_template,
        #"leads_file_path": file_path,
        "intents": [],  
        "responses": [], 
        "status": "setup", # NEXT STAGE IS emailready, emailsent
        "generated_email_path": ""
    }
    
    
    # Insert into MongoDB
    #campaigns_collection.insert_one(campaign_data)
    result = campaigns_collection.insert_one(campaign_data)

    # Convert `_id` to string for JSON response
    campaign_data["_id"] = str(result.inserted_id)

    return {"new_campaign_id": new_campaign_id, "status": "Campaign created successfully", "campaign": campaign_data}

@app.post("/generate_emails/")
async def generate_emails(campaign_id: str = Form(...),):

    campaign_data = campaigns_collection.find_one({"campaign_id": campaign_id}, {"_id": 0})  # Exclude `_id`
    if campaign_data:
        # campaign_name = campaign_data["campaign_name"]
        campaign_id = campaign_data["campaign_id"]
        email_template = campaign_data["email_template"]
        print("genrate email")
        generated_email_result = email_writer_module.generate_email( campaign_id, email_template)

        if generated_email_result==False:
            return {"status": "Failed to generate emails"}
        # Update campaign data in MongoDB
        campaigns_collection.update_one(
            {"campaign_id": campaign_id},
            {"$set": {
            # "generated_email_path": generated_email_path,
            "status": "emailready"
        }})
        return {"status": True}
    else:
        return {"status": "Failed to generate emails"}


@app.get("/campaign/get_emails/{campaign_id}")
def get_emails(campaign_id: str):
    
    emails = generated_emails_collection.find_one({"campaign_id": campaign_id}, {"_id": 0})

    if not emails:
        raise HTTPException(status_code=404, detail="No generated emails found for this campaign.")

    return {"emails": emails["data"]}

@app.post("/campaign/update_emails/{campaign_id}")
def update_emails(campaign_id: str, emails: list[dict]):
    
    # Update the emails in MongoDB (overwrite the existing "data" field)
    result = generated_emails_collection.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"data": emails}}
    )

    # Check if the campaign exists
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="No matching campaign found.")

    # Check if the update was successful
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update emails. No changes detected.")

    return {"status": "Success", "message": "Emails updated successfully."}

def start_campaign(id):
    url = f"https://api.instantly.ai/api/v2/campaigns/{id}/activate"
    headers = {
        'Authorization': f'Bearer {INS_API_KEY}',
    }
    response = requests.post(url, headers=headers)
    return response.json()

def add_leads_to_campaign(campaign_id: str):
 
    campaign_emails = generated_emails_collection.find_one({"campaign_id": campaign_id}, {"_id": 0, "data": 1})
    if not campaign_emails or "data" not in campaign_emails:
        raise HTTPException(status_code=404, detail="No generated emails found for this campaign.")

    url = "https://api.instantly.ai/api/v2/leads"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {INS_API_KEY}',
    }

    successful_uploads = 0
    failed_uploads = []

    for email_entry in campaign_emails["data"]:
        data = {
            "campaign": campaign_id,
            "email": email_entry["email"],
            "first_name": email_entry["username"],
            "last_name": email_entry["full_name"],
            "personalization": email_entry["email_pitch"]
        }


        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 201:  # Assuming 201 means successful creation######??????????? need comfirm
            successful_uploads += 1
        else:
            failed_uploads.append({
                "email": email_entry["email"],
                "error": response.text
            })

    return {
        "status": "Success",
        "message": f"{successful_uploads} leads added successfully.",
        "failed_uploads": failed_uploads
    }

""" add leads to campaign and start campaign. """
@app.post("/send_emails/")
async def send_emails(campaign_id: str = Form(...)):
    campaign_data = campaigns_collection.find_one({"campaign_id": campaign_id})
    
    if campaign_data:
        add_leads_to_campaign(campaign_id)
        start_campaign(campaign_id)
        
        campaigns_collection.update_one(
            {"campaign_id": campaign_id},
            {"$set": {"status": "emailsent"}}
        )
        
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