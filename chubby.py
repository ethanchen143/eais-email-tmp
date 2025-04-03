from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv("GPT_API_KEY")

# Helper function to extract only the influencer's response
def extract_influencer_response(email_body):
    """
    Step 1: Use GPT to extract only the influencer's response from the email chain,
    removing any initial outreach or previous correspondence.
    """
    # Configure your OpenAI client
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    prompt = f"""
    Extract ONLY the most recent response from the influencer from this email chain.
    Ignore any initial outreach message or previous correspondence.
    Return only the text that represents the influencer's latest response.
    
    EMAIL CONTENT:
    {email_body}
    """
    
    response = client.chat.completions.create(  # Changed to client.
        model="gpt-4o-mini", 
        messages=[
            {"role": "system", "content": "You are a helpful assistant that extracts only the most recent response from email chains."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    
    return response.choices[0].message.content.strip()

# Helper function to extract restaurant labels as a string array
def extract_restaurant_labels(influencer_response):
    """
    Step 2: Use GPT to extract the restaurants the influencer wants to work with
    and return them as a formatted string array.
    """
    # Configure your OpenAI client
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    prompt = f"""
    Based on the influencer's response below, identify which restaurant( they want to work with.
    Handle misspellings, and variations in naming.
    Return ONLY a string with the standardized names from the Chubby Group, (include the location), e.g."Las Vegas, NV (Chubby Cattle BBQ Las Vegas)".
    
    Known restaurants:
    - "Beverly Hills, CA (Chubby Curry – Covina)"
    - "Los Angeles, CA (Chubby Cattle Little Tokyo)"
    - "Monterey Park, CA (Chubby Cattle Monterey Park)"
    - "Cerritos, CA (Mikiya Wagyu Shabu House Cerritos)"
    - "Houston, TX (Mikiya Wagyu Shabu House Houston)"   
    - "Chicago, IL (Chubby Cattle Chicago)" 
    - "Chicago, IL (Wagyu House by The X Pot)"
    - "Las Vegas, NV (Chubby Cattle Las Vegas)"
    - "Las Vegas, NV (The X Pot Las Vegas)"
    - "Philadelphia, PA (Chubby Cattle Philadelphia)"
    
    If no specific restaurant is mentioned, (be strict if influencer says "i can work with any locations in Vegas") or it's unclear, only return "Ambiguous".
    
    INFLUENCER RESPONSE:
    {influencer_response}
    """
    
    response = client.chat.completions.create(  # Changed to client.
        model="gpt-4o-mini", 
        messages=[
            {"role": "system", "content": "You are a helpful assistant that extracts restaurant preferences from text."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    
    return response.choices[0].message.content.strip()

# Example usage:
if __name__ == "__main__":
    email = """
    Subject: Re: Collaboration Opportunity
    
    Hi there,
    Thanks for reaching out about the collaboration. I'm interested in working with Chubby Cattle Las Vegas and maybe the X Pot too.
    
    Best,
    Influencer
    
    On Mon, Mar 17, 2025 at 10:00 AM, Team <team@company.com> wrote:
    > Hi Influencer,
    > We're excited to offer you a collaboration opportunity with Chubby Group...
    """

    response = extract_influencer_response(email)
    print("Influencer Response:", response)
    
    restaurants = extract_restaurant_labels(response)
    print("Restaurants:", restaurants)