import json
import requests
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from email_writer import EmailWriter, GptOperations
import pandas as pd
import random
import string
import os
import copy
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from constants import get_keywords_prompt, get_aigen_campaign_name_prompt
from pymongo import MongoClient
import asyncio
from fastapi import Query, HTTPException
from typing import Dict
from difflib import get_close_matches
import re

load_dotenv()
VERSION = "1.0.1"
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

CAMPAIGN_ID = "a4682b71-34a6-4c82-bb4d-ed396b118e3e"
# CAMPAIGN_ID = "2ad45176-11ad-44d7-bd55-072ffba5363d"

MENU_PATTERN = re.compile(
    r'California:.*?Houston:.*?(?:Other Cities:.*?Houston:.*?)(?:\n|$)', 
    re.S | re.I
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # List the origins that should be allowed, or use ["*"] for all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

from base64 import b64decode
ZYTE_API_KEY = os.environ.get("ZYTE_API_KEY")

def scrape_page(url):
    api_response = requests.post(
        "https://api.zyte.com/v1/extract",
        auth=(ZYTE_API_KEY, ""),
        json={"url": url, "httpResponseBody": True},
    )
    
    http_response_body: bytes = b64decode(api_response.json()["httpResponseBody"])
    soup = BeautifulSoup(http_response_body, 'html.parser')
    
    page_text = soup.get_text(separator='\n')
    page_text = page_text.replace('\n', '').replace(' ', '')
    
    return page_text

@app.get("/get_keywords")
async def get_keywords(
    product_url: str = Query(...),
    brand_url: str = Query(...)
):
    product_page = scrape_page(product_url)
    brand_page = scrape_page(brand_url)
    get_keywords_prompt_for_ds = copy.deepcopy(get_keywords_prompt).format(
        brand = brand_page, product = product_page
    )

    client = OpenAI(api_key=OPENAI_API_KEY)
    completion = client.chat.completions.create(
        model="o4-mini",
        messages=[
            {"role": "system", "content": "You are a helpful marketing assistant that outputs JSON."},
            {"role": "user",   "content": get_keywords_prompt_for_ds}
        ]
    )

     # 4. Extract and parse the JSON response
    text = completion.choices[0].message.content
    try:
        keywords = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail=f"GPT returned invalid JSON: {text}")

    # 5. Validate
    if not (isinstance(keywords, list) and all(isinstance(k, str) for k in keywords)):
        raise HTTPException(status_code=400, detail="Response is not a JSON array of strings")

    return {"keywords": keywords}


@app.get("/get_aigen_campaign_name")
async def get_aigen_campaign_name(
    product_url: str = Query(...)
):
    ai_gen_campaignname = copy.deepcopy(get_aigen_campaign_name_prompt).format(product=product_url)
    response, status = gpt_ops_module.call_gpt_openai_json(prompt=ai_gen_campaignname, model="gpt-4o-mini")
    print(response)
    print(status)
    # Only accept a plain string as the campaign name
    if not isinstance(response, str) or not response.strip():
        raise HTTPException(status_code=400, detail="Response is not a valid campaign name string")
    return {"campaign_name": response.strip()}


from constants import get_product_info_prompt
@app.get("/get_product_info")
async def get_product_info(
    product_url: str = Query(...),
    brand_url: str = Query(...)
):
    # Scrape the pages (reusing your existing function)
    product_page = scrape_page(product_url)
    brand_page = scrape_page(brand_url)
    
    # Build the prompt manually without using format() to avoid JSON template issues
    product_info_prompt = copy.deepcopy(get_product_info_prompt).format(
        brand=brand_page, product=product_page
    )

    try:
        # Call the GPT model (reusing your existing module)
        response, status = gpt_ops_module.call_gpt_openai_json(
            prompt=product_info_prompt,
            model="gpt-4o-mini"
        )
        
        # Try to extract valid JSON from the response regardless of format
        product_info = extract_json_from_response(response)
        
        # Ensure all required fields exist with fallbacks
        product_info = ensure_complete_product_info(product_info)
        
        # Return the cleaned product information
        return product_info
    
    except Exception as e:
        print(f"Error in get_product_info: {str(e)}")
        # Return default values as fallback
        return {
            "companyName": "Company Name",
            "productName": "Product Name",
            "productSummary": "A versatile product designed to meet customer needs.",
            "sellingPoints": "Quality materials\nErgonomic design\nDurable construction\nCustomer satisfaction"
        }

def extract_json_from_response(response):
    """Extract valid JSON from various possible response formats."""
    if not isinstance(response, str):
        # Response is already parsed
        return response
    
    # Clean the response
    cleaned_response = response.strip()
    
    # Try to find JSON within markdown code blocks
    if "```" in cleaned_response:
        # Extract content between code blocks
        parts = cleaned_response.split("```")
        for i in range(1, len(parts), 2):  # Check odd-indexed parts (inside code blocks)
            try:
                # Remove potential language indicator (like "json")
                code_content = parts[i].strip()
                if code_content.startswith("json"):
                    code_content = code_content[4:].strip()
                
                return json.loads(code_content)
            except json.JSONDecodeError:
                continue  # Try next code block if this one fails
    
    # Try direct JSON parsing
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError:
        pass

    json_pattern = r'({[\s\S]*})'
    match = re.search(json_pattern, cleaned_response)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # If all parsing attempts fail, return empty dict
    print(f"Failed to parse response as JSON: {cleaned_response}")
    return {}

def ensure_complete_product_info(info):
    """Ensure all required fields exist in the product info."""
    if not isinstance(info, dict):
        info = {}
    
    # Define required fields with default values
    required_fields = {
        "companyName": "Company Name",
        "productName": "Product Name",
        "productSummary": "A versatile product designed to meet customer needs.",
        "sellingPoints": "Quality materials\nErgonomic design\nDurable construction\nCustomer satisfaction"
    }
    
    # Fill in missing fields
    for field, default_value in required_fields.items():
        if field not in info or not info[field]:
            info[field] = default_value
    
    return info

### CHUBBY GROUP INBOX CODE ###

import httpx
# get receieved, unread email, for autoreply
async def get_unread_emails():
    # Fetch emails from Instantly.ai API
    url = "https://api.instantly.ai/api/v2/emails"
    query = {
        "limit": "100",
        "campaign_id": CAMPAIGN_ID,
        "is_unread": "true",
        "ai_interest_value": "0.75", # Keep as string if API expects string
        "i_status": "1", # Keep as string if API expects string
        "email_type": "received"
    }
    headers = {
        'Authorization': f'Bearer {INS_API_KEY}',
        'Accept': 'application/json' # Good practice to include Accept header
    }
    try:
        # Use an async context manager for the client
        async with httpx.AsyncClient(timeout=30.0) as client: # Add a timeout
            # Use await for the async request method
            response = await client.get(url, headers=headers, params=query)
            response.raise_for_status()  # Raise exception for non-200 status codes
            return response.json()
    # httpx raises httpx.RequestError for connection issues, httpx.HTTPStatusError for 4xx/5xx
    except httpx.HTTPStatusError as e:
         print(f"API request failed with status {e.response.status_code}: {e.response.text}")
         # Decide what to return, maybe signal error differently?
         return {"items": [], "error": f"HTTP Status {e.response.status_code}"} # Match expected structure if possible
    except httpx.RequestError as e:
        print(f"API request connection failed: {e}")
        return {"items": [], "error": "Connection Error"} # Match expected structure if possible
    except Exception as e: # Catch other potential errors like JSON decoding
         print(f"An unexpected error occurred in get_unread_emails: {e}")
         return {"items": [], "error": "Unexpected Error"}

async def get_received_emails():
    # Fetch emails from Instantly.ai API
    url = "https://api.instantly.ai/api/v2/emails"
    query = {
        "limit": "100",
        "campaign_id": CAMPAIGN_ID,
        "i_status": "1", # Keep as string if API expects string
        "email_type": "received"
    }
    headers = {
        'Authorization': f'Bearer {INS_API_KEY}',
        'Accept': 'application/json'
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=query)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
         print(f"API request failed with status {e.response.status_code}: {e.response.text}")
         return {"items": [], "error": f"HTTP Status {e.response.status_code}"}
    except httpx.RequestError as e:
        print(f"API request connection failed: {e}")
        return {"items": [], "error": "Connection Error"}
    except Exception as e:
         print(f"An unexpected error occurred in get_all_emails: {e}")
         return {"items": [], "error": "Unexpected Error"}
    
async def get_sent_emails():
    # Fetch emails from Instantly.ai API
    url = "https://api.instantly.ai/api/v2/emails"
    query = {
        "limit": "100",
        "campaign_id": CAMPAIGN_ID,
        "i_status": "1", # Keep as string if API expects string
        "email_type": "sent"
    }
    headers = {
        'Authorization': f'Bearer {INS_API_KEY}',
        'Accept': 'application/json'
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=query)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
         print(f"API request failed with status {e.response.status_code}: {e.response.text}")
         return {"items": [], "error": f"HTTP Status {e.response.status_code}"}
    except httpx.RequestError as e:
        print(f"API request connection failed: {e}")
        return {"items": [], "error": "Connection Error"}
    except Exception as e:
         print(f"An unexpected error occurred in get_all_emails: {e}")
         return {"items": [], "error": "Unexpected Error"}

from datetime import datetime, timedelta

def format_date(timestamp_str):
    """Convert ISO timestamp to a more readable format"""
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        return timestamp.strftime("%A, %b %d, %Y at %I:%M %p")
    except ValueError:
        # Fallback if parsing fails
        return timestamp_str

from openai import OpenAI
OPENAI_API_KEY = os.getenv("GPT_API_KEY")

# File to store the cache
CACHE_FILE = "email_status_cache.json"

def load_cache():
    """Load the email status cache from file"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            # If the file is corrupted, start with a fresh cache
            return {}
    return {}

def save_cache(cache):
    """Save the email status cache to file"""
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

def get_restaurants():
    try:
        response = requests.get("https://backend.creatorain.com/", verify=False, timeout=10)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        data = response.json()
        
        # expects the response to be a dict with a 'restaurants' key
        restaurants = data.get("restaurants")
        if not isinstance(restaurants, list):
            print(f"Warning: Expected a list of restaurants, but got: {data}")
            return get_fallback_restaurants()

        return [
            {"name": r["name"], "location": r["location"], "priceRange": r["priceRange"]}
            for r in restaurants
        ]
    
    except (requests.exceptions.RequestException, requests.exceptions.JSONDecodeError, ValueError) as e:
        print(f"Error fetching restaurants from API: {e}")
        print("Using fallback restaurant data")
        return get_fallback_restaurants()

def get_fallback_restaurants():
    """Fallback restaurant data when the API is unavailable"""
    return [
        {"name": "Chubby Cattle BBQ Las Vegas", "location": "Las Vegas, NV", "priceRange": "$$"},
        {"name": "Chubby Cattle BBQ Los Angeles", "location": "Los Angeles, CA", "priceRange": "$$"},
        {"name": "Chubby Curry Covina", "location": "Los Angeles, CA", "priceRange": "$"},
        {"name": "Chubby Noodle House", "location": "Los Angeles, CA", "priceRange": "$"},
        {"name": "Chubby Steakhouse", "location": "Houston, TX", "priceRange": "$$$"},
    ]

# Removed extract_restaurant_labels function - no longer using restaurant backend

# generate label
def get_email_status(email_id, body_content, cache=None):
    """Get the email status, either from cache or by processing it"""
    if cache is None:
        cache = load_cache()
    # Check if the email ID is in the cache
    if str(email_id) in cache:
        return cache[str(email_id)]
    
    # Simplified status without restaurant backend calls
    print('Generating simple status label')
    
    # Simple keyword-based classification without external API calls
    body_lower = body_content.lower()
    
    if any(word in body_lower for word in ['interested', 'yes', 'love to', 'sounds good', 'great', 'awesome']):
        status = "Interested"
    elif any(word in body_lower for word in ['not interested', 'no thanks', 'pass', 'decline']):
        status = "Not Interested"
    else:
        status = "Pending Review"
    
    # Store in cache
    cache[str(email_id)] = status
    save_cache(cache)
    return status

def get_email_status_with_id(email_id):
    """Get the email status, either from cache or by processing it"""
    cache = load_cache()
    # Check if the email ID is in the cache
    if str(email_id) in cache:
        return cache[str(email_id)]
    else:
        return "nope"

# for demo frontend
@app.post("/get_emails_chubby/")
async def get_emails_chubby():
    # Fetch emails from Instantly.ai API
    received_response = await get_received_emails()
    received = received_response.get("items", [])
    
    # Load the cache once for the entire request
    cache = load_cache()
    transformed_emails = []
    
    for idx, email in enumerate(received):
        # Extract the body content - prefer plain text for simplicity
        body_content = ""
        if "body" in email:
            if isinstance(email["body"], dict):
                body_content = email["body"].get("text", email["body"].get("html", ""))
            else:
                body_content = str(email["body"])
        
        # Format the date
        date_str = format_date(email.get("timestamp_email", email.get("timestamp_created", "")))
    
        email_id = email.get("id") or idx + 1
        
        # Get status from cache or process it
        restaurant_label = get_email_status(email_id, body_content, cache)
        
        # Map Instantly.ai fields to your frontend model
        transformed_email = {
            "email_type": "received",
            "unread": email.get("is_unread",True),
            "id": email_id,
            "thread_id":email.get("thread_id"),
            "from": email.get("from_address_email", ""),
            "to": email.get("to_address_email_list", ""),
            "subject": email.get("subject", ""),
            "date": date_str,
            "status": restaurant_label,
            "body": body_content,
            "campaign": "Chubby Group Mega Campaign",
            "replies": []  # Initialize with empty replies
        }
        
        transformed_emails.append(transformed_email)

    sent_response = await get_sent_emails()
    sent = sent_response.get("items", [])
    for idx, email in enumerate(sent):
        # Extract the body content - prefer plain text for simplicity
        body_content = ""
        if "body" in email:
            if isinstance(email["body"], dict):
                body_content = email["body"].get("text", email["body"].get("html", ""))
            else:
                body_content = str(email["body"])
        
        # Format the date
        date_str = format_date(email.get("timestamp_email", email.get("timestamp_created", "")))
    
        email_id = email.get("id") or idx + 1
        
        # Get status from cache or process it
        restaurant_label = get_email_status(email_id, body_content, cache)
        
        # Map Instantly.ai fields to your frontend model
        transformed_email = {
            "email_type": "sent",
            "unread": email.get("is_unread",True),
            "id": email_id,
            "thread_id":email.get("thread_id"),
            "from": email.get("from_address_email", ""),
            "to": email.get("to_address_email_list", ""),
            "subject": email.get("subject", ""),
            "date": date_str,
            "status": restaurant_label,
            "body": body_content,
            "campaign": "Chubby Group Mega Campaign",
            "replies": []  # Initialize with empty replies
        }
        
        transformed_emails.append(transformed_email)
    
    # Return the transformed emails with CORS headers
    return transformed_emails

# for demo frontend data visualization
@app.get("/get_email_stats_chubby/")
async def get_email_stats_chubby():
    """
    Get statistics about positive replies/opportunities with day-by-day 
    accumulative data based on actual email received dates.
    
    Returns:
        Statistics with real data for positive replies and dummy data for other metrics
    """
    try:
        # Fetch all emails
        received_response = get_unread_emails()
        received = received_response.get("items", [])
        
        # Get the timestamp of each email and track positive replies by date
        email_dates = {}
        
        for email in received:
            # Extract the email timestamp (use timestamp_email or timestamp_created)
            timestamp_str = email.get("timestamp_email", email.get("timestamp_created", ""))
            
            if not timestamp_str:
                continue  # Skip emails without a timestamp
                
            # Parse the timestamp to a datetime object
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                date_str = timestamp.strftime("%Y-%m-%d")
                
                # Count each email as a positive reply (simplified version)
                if date_str not in email_dates:
                    email_dates[date_str] = 0
                email_dates[date_str] += 1
                
            except (ValueError, TypeError):
                # Skip emails with invalid timestamp format
                continue
        
        # Generate timeline data for the last 30 days
        today = datetime.now()
        timelineData = []
        
        # Track cumulative count
        cumulative_count = 0
        
        # Create a sorted list of dates for the last 30 days
        date_range = []
        for i in range(30):
            date = today - timedelta(days=29-i)
            date_str = date.strftime("%Y-%m-%d")
            date_range.append(date_str)
        
        # Build accumulative timeline
        for date_str in date_range:
            # Add any new emails from this date
            if date_str in email_dates:
                cumulative_count += email_dates[date_str]
            
            # Add data point to timeline
            timelineData.append({
                "date": date_str,
                "positiveReplies": cumulative_count,
                # Generate dummy data for other metrics based on the real positive replies count
                "videosInProgress": max(0, round(cumulative_count * 0.6)),
                "videosUploaded": max(0, round(cumulative_count * 0.3)),
                "commissionSent": max(0, round(cumulative_count * 0.15))
            })
        
        # Return the stats
        return {
            "stats": {
                "positiveReplies": cumulative_count,  # Total accumulative count
                # Scale dummy data based on real positive replies
                "videosInProgress": max(0, round(cumulative_count * 0.6)),
                "videosUploaded": max(0, round(cumulative_count * 0.3)),
                "commissionSent": max(0, round(cumulative_count * 0.15)),
                "timelineData": timelineData
            }
        }
        
    except Exception as e:
        print(f"Error getting email stats: {e}")
        return {
            "stats": {
                "positiveReplies": 0,
                "videosInProgress": 0,
                "videosUploaded": 0,
                "commissionSent": 0,
                "timelineData": []
            },
            "error": str(e)
        }

from pydantic import BaseModel
class LabelModificationRequest(BaseModel):
    email_id: str
    new_label: str
    
@app.post("/modify_email_label/")
async def modify_email_label(request: LabelModificationRequest):
    """
    Modifies the label and/or campaign of an email and updates the cache.
    
    Parameters:
    - email_id: The ID of the email to modify
    - new_label: The new restaurant label to assign
    - campaign: Optional campaign to assign to the email
    
    Returns:
    - Dictionary with success message and updated email details
    """
    try:
        email_id_str = str(request.email_id)
        
        # Update label cache
        label_cache = load_cache()
        label_cache[email_id_str] = request.new_label
        save_cache(label_cache)
                
        # Build response
        response = {
            "success": True,
            "message": "Email updated successfully",
            "email_id": request.email_id,
            "new_label": request.new_label
        }
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating email: {str(e)}"
        )

import html
from typing import Optional, Dict
class EmailReplyRequest(BaseModel):
    reply_to_uuid: str
    thread_id: str
    subject: str
    body: Dict[str, str]  # Can contain "html", "text" or both
    cc_address_email_list: Optional[str] = None
    bcc_address_email_list: Optional[str] = None
    eaccount: Optional[str] = None  # If None, will use the authenticated user's email

def text_to_html(text):
    """
    Convert plain text to HTML, properly handling newlines and basic formatting.
    """
    if not text:
        return ""
    escaped_text = html.escape(text)
    html_text = escaped_text.replace('\n', '<br>\n')
    html_text = f'<div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;">{html_text}</div>'
    return html_text

@app.post("/reply_to_email")
async def reply_to_email(request: EmailReplyRequest):
    """
    Reply to an existing email using the Instantly.ai API and then mark the thread as read.
    Ensures the body is in HTML format if only plain text is provided.
    """
    reply_api_response_data = None
    mark_as_read_status = {"success": False, "details": "Not attempted"}

    try:
        reply_payload = {
            "reply_to_uuid": request.reply_to_uuid,
            "subject": request.subject,
            "eaccount": request.eaccount
        }
        
        # Ensure we have HTML content
        body_dict = dict(request.body) 
        body_dict["html"] = text_to_html(body_dict["text"])
        reply_payload["body"] = body_dict

        # Add optional fields if they exist
        if request.cc_address_email_list:
            reply_payload["cc_address_email_list"] = request.cc_address_email_list

        if request.bcc_address_email_list:
            reply_payload["bcc_address_email_list"] = request.bcc_address_email_list

        # Call the Instantly.ai Reply API
        reply_url = "https://api.instantly.ai/api/v2/emails/reply"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {INS_API_KEY}'
        }

        reply_response = requests.post(reply_url, headers=headers, json=reply_payload)
        reply_api_response_data = reply_response.json() # Store response data regardless of status for potential debugging

        # Check for reply errors
        if reply_response.status_code != 200:
            return {
                "status": False,
                "message": f"Failed to send email reply. API Error: {reply_response.status_code}",
                "reply_details": reply_api_response_data,
                "mark_as_read_status": mark_as_read_status # Include initial status
            }

        # --- Reply was successful, now mark the thread as read ---
        try:
            mark_read_url = f"https://api.instantly.ai/api/v2/emails/threads/{request.thread_id}/mark-as-read"
            # Only Authorization header is needed for this endpoint based on docs
            mark_read_headers = {'Authorization': f'Bearer {INS_API_KEY}'}

            mark_read_response = requests.post(mark_read_url, headers=mark_read_headers)

            if mark_read_response.status_code == 200:
                mark_read_data = mark_read_response.json()
                mark_as_read_status["success"] = mark_read_data.get("success", False)
                mark_as_read_status["details"] = mark_read_data
                if not mark_as_read_status["success"]:
                     mark_as_read_status["message"] = "API indicated mark as read was not successful."
            else:
                print(f"Warning: Failed to mark thread {request.thread_id} as read. Status: {mark_read_response.status_code}, Response: {mark_read_response.text}")
                mark_as_read_status["success"] = False
                mark_as_read_status["details"] = {
                    "error": "API request failed",
                    "status_code": mark_read_response.status_code,
                    "response_text": mark_read_response.text
                }
                mark_as_read_status["message"] = "Failed to mark thread as read after sending reply."

        except Exception as mark_err:
            # Catch errors specifically during the mark-as-read call
            print(f"Error occurred while trying to mark thread {request.thread_id} as read: {str(mark_err)}")
            mark_as_read_status["success"] = False
            mark_as_read_status["details"] = {"error": f"Exception during mark-as-read call: {str(mark_err)}"}
            mark_as_read_status["message"] = "An exception occurred when trying to mark thread as read."

        # Return final success response including both results
        return {
            "status": True,
            "message": "Email reply sent successfully.",
            "reply_data": reply_api_response_data, # Data from the reply API call
            "mark_as_read_status": mark_as_read_status # Status of the mark-as-read call
        }

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions (like the one from sending account fetch)
        raise http_exc
    
    except Exception as e:
        # Catch general errors during reply preparation or sending
        print(f"Unhandled error in reply_to_email: {str(e)}") # Log the error
        return {
            "status": False,
            "message": f"Error processing email reply request: {str(e)}",
            "reply_details": reply_api_response_data, # Include if available
            "mark_as_read_status": mark_as_read_status
        }

@app.post("/forward_email")
async def forward_email(request: EmailReplyRequest):
    """
    Forward an existing email using the reply API endpoint.
    
    This endpoint is similar to reply_to_email but formats the email
    as a forward instead of a reply.
    """
    # The implementation is essentially the same as reply_to_email
    # but we might format the subject differently (add "Fwd: " prefix)
    if not request.subject.startswith("Fwd:"):
        request.subject = f"Fwd: {request.subject}"
    
    # Call the reply endpoint with the forward formatting
    return await reply_to_email(request)

from constants import restaurant_details
from collections import Counter

async def handle_email(
    body: str,
    influencer_email_address: str,
    influencer_name: str,
    marketer_email_address: str,
    marketer_name: str,
    subject: str,
    id: str,
    thread_id: str
):
    if len(influencer_name) == 0:
        influencer_name = influencer_email_address.split('@')[0].capitalize()
    marketer_name = marketer_name.replace("ChubbyGroup", "").replace("Chubby Group", "")

    body = re.sub(MENU_PATTERN, "", body)
    normalized_body = " ".join(body.casefold().split())

    variants = {
        "full_email": normalized_body,
    }

    for name, text in variants.items():
        # rebuild the user message each time with the new email text
        user_payload = json.dumps({
            "email": text,
        }, indent=2)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an intent classifier for influencer email replies of a restaurant collaboration campaign. You have sent an invitation email to this influencer.\n"
                    "Your task is to read the email content and classify it into **one** of the provided valid intents.\n"
                    "\n"
                    "Valid intents:\n"
                    "- Interested\n"
                    "- Interested No Location\n"
                    "- Compensation\n"

                    "- Not Interested\n"

                    "The interested intent is for direct interest only also they need to mention the location. If you return with 'interested', we are going to send 'Thank you so much for your interest, so excited that you’d like to collaborate with us! I’ve already contacted the manager of this location to check their availability for collaboration reservation. I’ll get back to you with the details as soon as I hear from them.'\n"
                    "The interested no location intent is for direct interest only but they don't need to mention the location. If you return with 'interested no location', we are going to send 'Thank you so much for your interest—so excited that you’d like to collaborate with us! Before we move forward, could you let us know which city or location you're based in (or where you'd like to collaborate)? That’ll help us coordinate with the right restaurant manager and check availability for your reservation.'\n"
                    "Compensation intent should encompass anything to do with payments, commission, or compensation, like mentioning rate, dollar sign, money amount, etc. If you return with 'compensation', we are going to send 'As compensation for your authentic coverage, we'd love to offer you and a guest a complimentary fine dining experience, typically valued between $120 and $180. We’re confident this will give you plenty of great content while experiencing firsthand the outstanding cuisine, ambiance, and service we’re known for. While additional monetary compensation isn't available for this particular collaboration, we hope this dining experience aligns well with your content style and audience engagement goals. Please let us know your preferred location / restaurant if you're interested in moving forward.'\n"
                    
                    "**Return ONLY a JSON object in this format:**\n"
                    "{\"intent\": \"<one of the valid intents>\"}\n"
                    "Do not return explanations, extra text, or formatting. No bullet points, no summaries — just the JSON.\n"
                    "If the intent is unclear or not in the list, return: {\"intent\": \"Ambiguous\"}"
                )
            },
            {
                "role": "user",
                "content": user_payload
            }
        ]

        resp, _ = gpt_ops_module.call_gpt_openai(
            messages,
            model="gpt-4.1-mini",
            temperature=0,
            max_tokens=20
        )

        # Parse the intent from the response
        if isinstance(resp, dict):
            intent = resp.get("intent", "").strip()
        elif isinstance(resp, str):
            try:
                # Try to parse as JSON first
                parsed_resp = json.loads(resp)
                intent = parsed_resp.get("intent", "").strip()
            except json.JSONDecodeError:
                # If JSON parsing fails, use the string as-is
                intent = resp.strip()
        else:
            intent = str(resp).strip()

    request = LabelModificationRequest(email_id=thread_id, new_label=intent)
    await modify_email_label(request)

    print("Handling email:", body[:30])
    print("Intent:", intent)

    if intent not in ["Interested", "Compensation", "Not Interested", "Ambiguous"]:
        intent = "Ambiguous"

    if "Ambiguous" in intent:
        # do nothing
        return

    elif intent == "Not Interested":
        # do nothing
        return

    elif intent == "Interested":
        response = f"""
        Hi {influencer_name},
        Thank you so much for your interest, so excited that you’d like to collaborate with us! I’ve already contacted the manager of this location to check their availability for collaboration reservation. I’ll get back to you with the details as soon as I hear from them.

        Talk to you very soon!
        Chubby Group Collaboration Team
        """

    elif intent == "Interested No Location":
        response = f"""
        Hi {influencer_name},
        Thank you so much for your interest—so excited that you’d like to collaborate with us! Before we move forward, could you let us know which city or location you're based in (or where you'd like to collaborate)? That’ll help us coordinate with the right restaurant manager and check availability for your reservation.

        Looking forward to your reply!
        Chubby Group Collaboration Team
        """

    elif intent == "Compensation":
        response = f"""
        Hi {influencer_name},
        As compensation for your authentic coverage, we'd love to offer you and a guest a complimentary fine dining experience, typically valued between $120 and $180. We’re confident this will give you plenty of great content while experiencing firsthand the outstanding cuisine, ambiance, and service we’re known for.
        While additional monetary compensation isn't available for this particular collaboration, we hope this dining experience aligns well with your content style and audience engagement goals.
        Please let us know your preferred location / restaurant if you're interested in moving forward.

        Best,
        Chubby Group Collaboration Team
        """

    request = EmailReplyRequest(
        reply_to_uuid=id,
        thread_id=thread_id,
        subject=subject,
        body={"text": response},
        eaccount=marketer_email_address
    )

    await reply_to_email(request)

    print("email sent:", response)
    print("--------------------------------")


# async def auto_reply_process(campaign_id: str, intents: List[str], responses: List[str]):
async def auto_reply_process(campaign_id: str):
    while True:
        try: 
            emails_data = await get_unread_emails() # Assuming it becomes async
            emails = emails_data.get('items', [])
        except Exception as fetch_err:
            print(f"Error fetching emails for {campaign_id}: {fetch_err}")
            await asyncio.sleep(60) # Wait before retrying fetch
            continue # Skip this iteration

        for email in emails:
            try:
                subject = email.get('subject', 'No Subject')
                body = email.get('body', {}).get('text', '')
                email_id = email.get('id')
                thread_id = email.get('thread_id')
                from_address_list = email.get('from_address_json', [])
                to_address_list = email.get('to_address_json', [])

                if not all([email_id, thread_id, from_address_list, to_address_list, body]):
                     print(email_id, thread_id, from_address_list, to_address_list, body)
                     print(f"Skipping email due to missing critical info: {email.get('id', 'N/A')}")
                     continue
                
                # avoid sending twice
                # label = get_email_status_with_id(email_id)
                thread_label = get_email_status_with_id(thread_id)
                if thread_label in ["Interested", "Compensation","Not Interested", "Ambiguous"]:
                    print(f"Skipping email due to already replied (label check): {body[:50]}")
                    continue

                if "I’ve already contacted the manager of this location to check their availability for collaboration reservation" in body:
                    print(f"Skipping email due to already replied (auto check): {body[:50]}")
                    continue

                if "Looking forward to talk to you soon!" in body:
                    print(f"Skipping email because already manually replied (manual check): {body[:50]}")
                    continue

                influencer_email_address = from_address_list[0].get('address')
                influencer_name = from_address_list[0].get('name', influencer_email_address) # Use email as fallback name
                marketer_email_address = to_address_list[0].get('address')
                marketer_name = to_address_list[0].get('name', marketer_email_address)

                if not all([influencer_email_address, marketer_email_address]):
                     print(f"Skipping email due to missing address info: {email_id}")
                     continue

                await handle_email(body, influencer_email_address, influencer_name, marketer_email_address, marketer_name, subject, email_id, thread_id)


            except (KeyError, IndexError, TypeError) as parse_err:
                print(f"Error processing email {email.get('id', 'N/A')} for {campaign_id}: {parse_err}")
            except Exception as handle_err:
                print(f"Unexpected error handling email {email.get('id', 'N/A')} for {campaign_id}: {handle_err}")

        await asyncio.sleep(600)

active_tasks = {}

@app.post("/set_auto_reply/")
# async def set_auto_reply(campaign_id: str = Form(...),    
#                           intents: List[str] = Form([]),  
#                           responses: List[str] = Form([]) ):
async def set_auto_reply(campaign_id: str = Form(...)):
    if campaign_id in active_tasks:
        active_tasks[campaign_id].cancel()
    task = asyncio.create_task(auto_reply_process(campaign_id))
    active_tasks[campaign_id] = task
    return {"status": "Success", "message": f"Auto Reply started for Campaign {campaign_id}"}

@app.post("/stop_auto_reply/")
async def stop_auto_reply(campaign_id: str = Form(...)):
    task = active_tasks.pop(campaign_id, None)
    if task:
        task.cancel()
        return {"status": "Success", "message": f"Auto Reply stopped for Campaign {campaign_id}"}
    return {"status": "Fail", "message": f"No auto reply process found for Campaign {campaign_id}"}

# Instantly.ai auto campaign creation - done manually

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


# """ add campaignn: create campaign, link the sending accounts to campaign, store campaign info """
# @app.post("/add_campaign/")
# async def add_campaign(
#     name: str = Form(...),
#     initial_email_template: str = Form(""),
#     email_title: str = Form(""),
#     file: UploadFile = File(...)
# ):
#     # Generate a random suffix to avoid duplicate names
#     random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
#     unique_name = f"{name}_{random_suffix}"  # Append random suffix to the name

#     if not email_title:
#         email_title = "Hello {{firstName}}!"
#     new_campaign_id = create_campaign(unique_name, email_title)['id']

#     try:
#             content = await file.read()
#             data = pd.read_csv(pd.io.common.BytesIO(content))  # Read CSV as Pandas DataFrame

#             # Convert DataFrame to structured format
#             lead_data = []
#             for _, row in data.iterrows():
#                 lead_data.append({
#                     "username": row["username"],
#                     "name": row["full_name"],
#                     "bio": row["bio"],
#                     "desc": row["video_desc"],
#                     "email": row["email"],
#                 })

#             # Insert leads under campaign_id
#             leads_collection.insert_one({
#                 "campaign_id": new_campaign_id,
#                 "data": lead_data
#             })
        
#             #await f.write(content)
#     except Exception as e:
#         return {"status": f"File upload failed: {str(e)}"}

#     # Prepare campaign data
#     campaign_data = {
#         "campaign_name": unique_name,
#         "campaign_id": new_campaign_id,
#         "email_template": initial_email_template,
#         #"leads_file_path": file_path,
#         "intents": [],  
#         "responses": [], 
#         "status": "setup", # NEXT STAGE IS emailready, emailsent
#         "generated_email_path": ""
#     }
    
#     # Insert into MongoDB
#     #campaigns_collection.insert_one(campaign_data)
#     result = campaigns_collection.insert_one(campaign_data)

#     # Convert `_id` to string for JSON response
#     campaign_data["_id"] = str(result.inserted_id)

#     return {"new_campaign_id": new_campaign_id, "status": "Campaign created successfully", "campaign": campaign_data}

# @app.post("/generate_emails/")
# async def generate_emails(campaign_id: str = Form(...),):

#     campaign_data = campaigns_collection.find_one({"campaign_id": campaign_id}, {"_id": 0})  # Exclude `_id`
#     if campaign_data:
#         # campaign_name = campaign_data["campaign_name"]
#         campaign_id = campaign_data["campaign_id"]
#         email_template = campaign_data["email_template"]
#         generated_email_result = email_writer_module.generate_email( campaign_id, email_template)

#         if generated_email_result==False:
#             return {"status": "Failed to generate emails"}
#         # Update campaign data in MongoDB
#         campaigns_collection.update_one(
#             {"campaign_id": campaign_id},
#             {"$set": {
#             # "generated_email_path": generated_email_path,
#             "status": "emailready"
#         }})
#         return {"status": True}
#     else:
#         return {"status": "Failed to generate emails"}

# @app.get("/campaign/get_emails/{campaign_id}")
# def get_emails(campaign_id: str):
    
#     emails = generated_emails_collection.find_one({"campaign_id": campaign_id}, {"_id": 0})

#     if not emails:
#         raise HTTPException(status_code=404, detail="No generated emails found for this campaign.")

#     return {"emails": emails["data"]}

# @app.post("/campaign/update_emails/{campaign_id}")
# def update_emails(campaign_id: str, emails: list[dict]):

#     # Update the emails in MongoDB (overwrite the existing "data" field)
#     result = generated_emails_collection.update_one(
#         {"campaign_id": campaign_id},
#         {"$set": {"data": emails}}
#     )

#     # Check if the campaign exists
#     if result.matched_count == 0:
#         raise HTTPException(status_code=404, detail="No matching campaign found.")

#     # Check if the update was successful
#     if result.modified_count == 0:
#         raise HTTPException(status_code=500, detail="Failed to update emails. No changes detected.")

#     return {"status": "Success", "message": "Emails updated successfully."}

# def start_campaign(id):
#     url = f"https://api.instantly.ai/api/v2/campaigns/{id}/activate"
#     headers = {
#         'Authorization': f'Bearer {INS_API_KEY}',
#     }
#     response = requests.post(url, headers=headers)
#     return response.json()

# def add_leads_to_campaign(campaign_id: str):
#     campaign_emails = generated_emails_collection.find_one({"campaign_id": campaign_id}, {"_id": 0, "data": 1})
#     if not campaign_emails or "data" not in campaign_emails:
#         raise HTTPException(status_code=404, detail="No generated emails found for this campaign.")

#     url = "https://api.instantly.ai/api/v2/leads"
#     headers = {
#         'Content-Type': 'application/json',
#         'Authorization': f'Bearer {INS_API_KEY}',
#     }

#     successful_uploads = 0
#     failed_uploads = []

#     for email_entry in campaign_emails["data"]:
#         data = {
#             "campaign": campaign_id,
#             "email": email_entry["email"],
#             "first_name": email_entry["username"],
#             "last_name": email_entry["full_name"],
#             "personalization": email_entry["email_pitch"]
#         }

#         response = requests.post(url, headers=headers, json=data)

#         if response.status_code == 200:  
#             successful_uploads += 1
#         else:
#             failed_uploads.append({
#                 "email": email_entry["email"],
#                 "error": response.text
#             })
        
#     return {
#         "status": "Success",
#         "message": f"{successful_uploads} leads added successfully.",
#         "failed_uploads": failed_uploads
#     }

# """ add leads to campaign and start campaign. """
# @app.post("/send_emails/")
# async def send_emails(campaign_id: str = Form(...)):
#     campaign_data = campaigns_collection.find_one({"campaign_id": campaign_id})
#     if campaign_data:
#         add_leads_to_campaign(campaign_id)
#         start_campaign(campaign_id)
#         campaigns_collection.update_one(
#             {"campaign_id": campaign_id},
#             {"$set": {"status": "emailsent"}})
#         return {"status": True}
#     else:
#         return {"status": "Failed to send emails"}