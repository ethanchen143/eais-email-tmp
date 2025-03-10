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
import asyncio

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

from scrapingbee import ScrapingBeeClient
SCRAPING_KEY = os.environ.get("SCRAPING_KEY")

def scrape_page(url):
    url = url.strip('/')
    client = ScrapingBeeClient(api_key=SCRAPING_KEY)
    try:
        response = client.get(url)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to retrieve {url}: {e}")
        return
    soup = BeautifulSoup(response.content, 'html.parser')
    page_text = soup.get_text(separator='\n').strip()
    page_text = page_text.replace('\n', '').replace(' ', '')
    return page_text

@app.get("/get_keywords")
async def get_keywords(
    product_url: str = Query(...),
    brand_url: str = Query(...)
):
    product_page = scrape_page(product_url)
    brand_page = scrape_page(brand_url)
    print(product_page)
    print(brand_page)
    get_keywords_prompt_for_ds = copy.deepcopy(get_keywords_prompt).format(
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

        if response.status_code == 200:  
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
            {"$set": {"status": "emailsent"}})
        return {"status": True}
    else:
        return {"status": "Failed to send emails"}

def get_unread_emails(campaign_id):
    url = "https://api.instantly.ai/api/v2/emails"
    query = {
    "limit": "10",
    "campaign_id": "c8262413-40fc-4916-85d9-84fb7cb63692",
    "is_unread": "true",
    "email_type": "received"
    }
    headers = {
        'Authorization': f'Bearer {INS_API_KEY}',
    }
    response = requests.get(url, headers=headers, params=query)
    return response.json()

def handle_email(body,influencer_email_address,influencer_name,marketer_email_address,marketer_name, intents, responses):
    # identify intent
    # reply using email template
    return None

active_tasks = {}

async def auto_reply_process(campaign_id: str, intents: List[str], responses: List[str]):
    while True:
        emails = get_unread_emails(campaign_id)['items']
        for email in emails:
            body = email['body']['text']
            influencer_email_address = email['from_address_json'][0]['address']
            influencer_name = email['from_address_json'][0]['name']
            marketer_email_address = email['to_address_json'][0]['address']
            marketer_name = email['to_address_json'][0]['name']
            handle_email(body, influencer_email_address, influencer_name, marketer_email_address, marketer_name, intents, responses)
        await asyncio.sleep(300)

@app.post("/set_auto_reply/")
async def set_auto_reply(campaign_id: str = Form(...),    
                          intents: List[str] = Form([]),  
                          responses: List[str] = Form([]) ):
    if campaign_id in active_tasks:
        active_tasks[campaign_id].cancel()
    task = asyncio.create_task(auto_reply_process(campaign_id, intents, responses))
    active_tasks[campaign_id] = task
    return {"status": "Success", "message": f"Auto Reply started for Campaign {campaign_id}"}

@app.post("/stop_auto_reply/")
async def set_auto_reply(campaign_id: str = Form(...)):
    task = active_tasks.pop(campaign_id, None)
    if task:
        task.cancel()
        return {"status": "Success", "message": f"Auto Reply stopped for Campaign {campaign_id}"}
    return {"status": "Fail", "message": f"No auto reply process found for Campaign {campaign_id}"}