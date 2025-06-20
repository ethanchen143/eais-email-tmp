from constants import generate_pitch_prompt
import pandas as pd
import copy
import os
import tiktoken
import requests
from requests.exceptions import Timeout
from dotenv import load_dotenv
from pymongo import MongoClient
import json
load_dotenv()

GPT_API_KEY = os.environ.get("GPT_API_KEY")
GPT_URL = os.environ.get("GPT_URL")
DS_API_KEY = os.environ.get("DS_API_KEY")

# MongoDB Connection
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE_NAME = os.getenv("MONGODB_DATABASE_NAME")

client = MongoClient(MONGODB_URI)
db = client[MONGODB_DATABASE_NAME]
generated_emails_collection = db["generated_emails"]  
leads_collection = db["leads"]  

class GptOperations:
    max_tokens = 2000
    def __init__(self, model="gpt-4o-mini"):
        self.model = model
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self,text: str):
        """Returns the number of tokens in a text string."""
        num_tokens = len(self.encoding.encode(text))
        return num_tokens

    def get_remaining_tokens(self, prompt_elements:list,tokens_limit=None):
        """Returns the remaining number of tokens that are left given a list of str elements"""
        remaining_tokens = tokens_limit if tokens_limit else self.max_tokens
        for element in prompt_elements:
            remaining_tokens -= (self.count_tokens(element) + 9)
        return remaining_tokens
    
    def get_remaining_tokens_prompt_dict(self, prompt_element,tokens_limit=None):
        """Returns the remaining number of tokens that are left given a list of str elements"""
        remaining_tokens = tokens_limit if tokens_limit else self.max_tokens
        remaining_tokens -= (self.count_tokens("role:"))
        remaining_tokens -= (self.count_tokens(prompt_element["role"]))
        remaining_tokens -= (self.count_tokens("content:"))
        remaining_tokens -= (self.count_tokens(prompt_element["content"]))
        return remaining_tokens

    def call_gpt_openai(self, context, model=None, temperature=0, max_tokens=3500, timeout=10):
        context = copy.deepcopy(context)
        for message in context:
            message.pop("time_stamp", None)
        
        model = model if model else self.model
        
        url = GPT_URL
        api_key = GPT_API_KEY
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": model,
            "messages": context,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 1,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0
        }

        error = "None"
        tokens = sum(self.count_tokens(message["content"]) + 7 for message in context)
        
        try:
            response = requests.post(url=url, headers=headers, json=data, timeout=timeout)
            response.raise_for_status()
            result = response.json()
            message = "Success"
            return result['choices'][0]['message']['content'], {"tokens": tokens, "message": message, "error": error}
        except Timeout as e:
            message = f"The Request Timed out: {str(e)}"
            error = str(e)
        except Exception as e:
            message = f"An unexpected error occurred: {str(e)}"
            error = str(e)
        return False, {"tokens": tokens, "message": message, "error": error}

    def call_gpt_openai_json(self, prompt, model=None, temperature=0, max_tokens=2000, timeout=40):
        context = [{"role": "system", "content": prompt}]
        return self.call_gpt_openai(context, model, temperature, max_tokens, timeout)

class EmailWriter:
    def __init__(self):
        self.gpt_ops = GptOperations(model="gpt-4o-mini")
        self.type = type

    def generate_pitch(self,username,name,bio,desc,email_template):
        generate_pitch_prompt_for_gpt = copy.deepcopy(generate_pitch_prompt).format(
            username=username,name=name,bio=bio,desc=desc,email=email_template
        )
        pitch_response_full_email, status = self.gpt_ops.call_gpt_openai_json(prompt=generate_pitch_prompt_for_gpt,model="gpt-4o-mini")
        return pitch_response_full_email

    def generate_email(self, campaign_id, email_template):
        try:
            # Fetch leads from MongoDB instead of reading a CSV
            leads_data = leads_collection.find_one({"campaign_id": campaign_id}, {"_id": 0})
            if not leads_data:
                print(f"Error: No leads found for campaign_id {campaign_id}")
                return False  

            emails = []

            for lead in leads_data["data"]:
                username = lead["username"]
                name = lead["name"]
                bio = lead["bio"]
                desc = lead["desc"]
                email = lead["email"]

                 # Generate personalized email content
                email_pitch = self.generate_pitch(username, name, bio, desc, email_template)
                emails.append({
                    "username": username,
                    "full_name": name,
                    "email_pitch": email_pitch,
                    "bio": bio,
                    "video_desc": desc,
                    "email": email
                })
            
            # Store or update generated emails in MongoDB
            generated_emails_collection.update_one(
            {"campaign_id": campaign_id},  # Query to find the existing document
            {"$set": {"data": emails}},  # Update the "data" field with new emails
            upsert=True  # If no document exists, create a new one
            )           

            return True
    
        except Exception as e:
            print(f"Error in generate_email: {str(e)}")  
            return False  
        
    # def get_intent(self, message):
    #     reply_intent_prompt_for_gpt = copy.deepcopy(reply_intent_prompt).format(
    #         user_message = message
    #     )
    #     reply_intent_response, status = self.ds_ops.call_gpt_openai_json(prompt=reply_intent_prompt_for_gpt,model="gpt-4o")
    #     reply_intent_response = json.loads(reply_intent_response)
    #     return reply_intent_response['intent']

    # def seeking_human_for_other_task_response(self, message):
    #     human_needed_prompt_for_gpt = copy.deepcopy(human_needed_prompt).format(
    #         influencer_response = message
    #     )
    #     reply_response, status = self.ds_ops.call_gpt_openai_json(prompt=human_needed_prompt_for_gpt,model="gpt-4o")
    #     reply_response = json.loads(reply_response)
    #     return reply_response['message']

    # def respond_to_reply(self, email_id, campaign_id, message):
    #     campaingn = self.redis_db.read(campaign_id)
    #     if campaingn:
    #         message_intent = self.get_intent(message)
    #         lead_index = self.get_email_index(campaingn, email_id)
    #         first_name = campaingn[lead_index][email_id]['influencer name'].split(' ')[0].title()
    #         response = False
    #         if message_intent == "paid_collaboration":
    #             response = copy.deepcopy(paid_collaboration_response).format(lead_name = first_name)
    #         elif message_intent == "program_inquiry":
    #             response = copy.deepcopy(program_inquiry_response).format(lead_name = first_name)
    #         elif message_intent == "next_steps":
    #             response = copy.deepcopy(next_steps_response).format(lead_name = first_name)
    #         elif message_intent == "product_request":
    #             response = copy.deepcopy(product_request_response).format(lead_name = first_name)
    #         elif message_intent == "other":
    #             response = self.seeking_human_for_other_task_response(message=message)
    #         else:
    #             return False
    #         if "replies" not in campaingn[lead_index][email_id]:
    #             campaingn[lead_index][email_id]['replies'] = []
    #         reply = {
    #             'recieved_reply': message,
    #             'reply_intent': message_intent,
    #             'sent_reply': response,
    #         }
    #         campaingn[lead_index][email_id]['replies'].append(reply)      
    #         self.redis_db.write(campaign_id, campaingn)
    #         return response
    #     return False
        
# DS_API_KEY = os.environ.get("DS_API_KEY")

# class DeepSeekOperations:
#     max_tokens = 2000 
#     def __init__(self, model="deepseek-chat"):
#         self.model = model
#         self.encoding = tiktoken.get_encoding("cl100k_base")
        
#     def count_tokens(self, text: str):
#         return len(self.encoding.encode(text))
    
#     def get_remaining_tokens(self, prompt_elements: list, tokens_limit=None):
#         remaining_tokens = tokens_limit if tokens_limit else self.max_tokens
#         for element in prompt_elements:
#             remaining_tokens -= (self.count_tokens(element) + 9)
#         return remaining_tokens
    
#     def get_remaining_tokens_prompt_dict(self, prompt_element, tokens_limit=None):
#         remaining_tokens = tokens_limit if tokens_limit else self.max_tokens
#         remaining_tokens -= (self.count_tokens("role:"))
#         remaining_tokens -= (self.count_tokens(prompt_element["role"]))
#         remaining_tokens -= (self.count_tokens("content:"))
#         remaining_tokens -= (self.count_tokens(prompt_element["content"]))
#         return remaining_tokens
    
#     def call_deepseek_api(
#         self, 
#         context, 
#         model=None, 
#         temperature=0, 
#         max_tokens=3500, 
#         timeout=10
#     ):
#         context = copy.deepcopy(context)
#         for message in context:
#             message.pop("time_stamp", None)
        
#         model = model or self.model
        
#         # DeepSeek API endpoint and key
#         url = "https://api.deepseek.com/v1/chat/completions"
#         api_key = DS_API_KEY
        
#         headers = {
#             "Content-Type": "application/json",
#             "Authorization": f"Bearer {api_key}",
#             "Accept": "application/json"
#         }
        
#         data = {
#             "model": model,
#             "messages": context,
#             "temperature": temperature,
#             "max_tokens": max_tokens,
#             "top_p": 1,
#             "frequency_penalty": 0.0,
#             "presence_penalty": 0.0
#         }
        
#         error = "None"
#         tokens = sum(self.count_tokens(msg["content"]) + 7 for msg in context)
        
#         try:
#             response = requests.post(
#                 url=url, 
#                 headers=headers, 
#                 json=data, 
#                 timeout=timeout
#             )
#             response.raise_for_status()
#             result = response.json()
#             return (
#                 result['choices'][0]['message']['content'], 
#                 {"tokens": tokens, "message": "Success", "error": error}
#             )
#         except requests.exceptions.Timeout as e:
#             error = f"Timeout: {str(e)}"
#         except Exception as e:
#             error = f"Error: {str(e)}"
        
#         return False, {"tokens": tokens, "message": error, "error": error}
    
#     def call_deepseek_json(
#         self, 
#         prompt, 
#         model=None, 
#         temperature=0, 
#         max_tokens=2000, 
#         timeout=40
#     ):
#         context = [{"role": "system", "content": prompt}]
#         return self.call_deepseek_api(
#             context, 
#             model, 
#             temperature, 
#             max_tokens, 
#             timeout
#         )
    
# class EmailWriter:
#     def __init__(self):
#         self.ds_ops = DeepSeekOperations()
#         self.type = type

#     def generate_pitch(self,username,name,bio,desc,email_template):
#         generate_pitch_prompt_for_ds = copy.deepcopy(generate_pitch_prompt).format(
#             username=username,name=name,bio=bio,desc=desc,email=email_template
#         )
#         pitch_response_full_email, status = self.ds_ops.call_deepseek_json(prompt=generate_pitch_prompt_for_ds,model="deepseek-chat")
#         return pitch_response_full_email

#     def generate_email(self, file_path, cmp_id, email_template):
#         df = pd.read_csv(file_path, encoding='utf-8')
#         emails = []
#         for index, row in df.iterrows():
#             username = row['username']
#             name = row['full_name']
#             bio = row['bio']
#             desc = row['video_desc']
#             email = row['email'] # email address

#             # influencer_profiling_response = self.get_influencer_profile(username,name,bio,desc)
#             email_pitch = self.generate_pitch(username,name,bio,desc,email_template)
#             emails.append({
#                 "username": username,
#                 "full_name": name,
#                 "email_pitch": email_pitch,
#                 "bio": bio,
#                 "video_desc": desc,
#                 "email": email
#             })
            
#         generated_email_path = os.path.join("emails", f"generated_emails_{cmp_id}.csv")
#         os.makedirs(os.path.dirname(generated_email_path), exist_ok=True)
#         pd.DataFrame(emails).to_csv(generated_email_path, index=False, encoding='utf-8')
#         return generated_email_path
    
    # def get_email_index(self, campaign_data, email):
    #     for index, lead in enumerate(campaign_data):
    #         if email in lead:
    #             return index
    #     return None

    # def get_influencer_profile(self, influencer_user_name, influencer_name, influencer_bio, video_descriptions):
    #     influencer_profiling_prompt_for_gpt = copy.deepcopy(influencer_profiling_prompt).format(
    #         influencer_user_name = influencer_user_name,
    #         influencer_name = influencer_name,
    #         influencer_bio = influencer_bio,
    #         video_descriptions = video_descriptions
    #     )
    #     influencer_profiling_response, status = self.ds_ops.call_gpt_openai_json(prompt=influencer_profiling_prompt_for_gpt,model="gpt-4o-mini")
    #     influencer_profiling_response = json.loads(influencer_profiling_response)
    #     return influencer_profiling_response

    # def get_intent(self, message):
    #     reply_intent_prompt_for_gpt = copy.deepcopy(reply_intent_prompt).format(
    #         user_message = message
    #     )
    #     reply_intent_response, status = self.ds_ops.call_gpt_openai_json(prompt=reply_intent_prompt_for_gpt,model="gpt-4o")
    #     reply_intent_response = json.loads(reply_intent_response)
    #     return reply_intent_response['intent']


    # def seeking_human_for_other_task_response(self, message):
    #     human_needed_prompt_for_gpt = copy.deepcopy(human_needed_prompt).format(
    #         influencer_response = message
    #     )
    #     reply_response, status = self.ds_ops.call_gpt_openai_json(prompt=human_needed_prompt_for_gpt,model="gpt-4o")
    #     reply_response = json.loads(reply_response)
    #     return reply_response['message']

    # def respond_to_reply(self, email_id, campaign_id, message):
    #     campaingn = self.redis_db.read(campaign_id)
    #     if campaingn:
    #         message_intent = self.get_intent(message)
    #         lead_index = self.get_email_index(campaingn, email_id)
    #         first_name = campaingn[lead_index][email_id]['influencer name'].split(' ')[0].title()
    #         response = False
    #         if message_intent == "paid_collaboration":
    #             response = copy.deepcopy(paid_collaboration_response).format(lead_name = first_name)
    #         elif message_intent == "program_inquiry":
    #             response = copy.deepcopy(program_inquiry_response).format(lead_name = first_name)
    #         elif message_intent == "next_steps":
    #             response = copy.deepcopy(next_steps_response).format(lead_name = first_name)
    #         elif message_intent == "product_request":
    #             response = copy.deepcopy(product_request_response).format(lead_name = first_name)
    #         elif message_intent == "other":
    #             response = self.seeking_human_for_other_task_response(message=message)
    #         else:
    #             return False
    #         if "replies" not in campaingn[lead_index][email_id]:
    #             campaingn[lead_index][email_id]['replies'] = []
    #         reply = {
    #             'recieved_reply': message,
    #             'reply_intent': message_intent,
    #             'sent_reply': response,
    #         }
    #         campaingn[lead_index][email_id]['replies'].append(reply)      
    #         self.redis_db.write(campaign_id, campaingn)
    #         return response
    #     return False