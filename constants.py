generate_pitch_prompt = """
### Role and Task:
You are a seasoned marketing strategist specializing in influencer partnerships. Craft a compelling pitch from the provided email template.
Customize the keyword in brackets based on the provided influencer information.

### Influencer Profile:
username:{username}
full name:{name}
bio:{bio}
desc:{desc}

### Base Email:
{email}

### Desired Tone and Style:
* Match the influencer's specific personality traits, e.g., humorous, relatable.
* Maintain a professional yet friendly tone.
* Adjust the content to match the influencer's personal profile. Do not use complex words and grammar, use simple and casuall vocabulary that are used in daily routine.
* The text should be written from the perspective of the marketing agent personally reaching out, showing their genuine interest.
* Make proper use of new lines.
* Make sure the there is no redundancy in the messages.

### Output Format:
Do not print greetings or signature, directly output only the main body (like the template).
"""

# influencer_profiling_prompt = """
# ### Task:
# consider the following information of a influencer and determine the profession, type of influencer, goal of content, type of content, type of audience they target.

# ### Input:
# Username: {influencer_user_name}

# Name: {influencer_name}

# Bio: "{influencer_bio}"

# Video descriptions: {video_descriptions}

# ### Output Format:
# Provide the results in a JSON format following RFC8259, like this:
# {{
#   "profession": "<profession>",
#   "influencer name": "<actual name of the influencer, remove any attributes which are not name>",
#   "type of influencer": "<type of influencer>",
#   "goal of content": "<goal of content (descriptive)>",
#   "type of content": "<type of content (descriptive)>",
#   "personality description": "<personality description of the influencer, likes, dislikes etc (descriptive)>",
#   "type of audience they target": "<type of audience they target (descriptive)>"
# }}
# """

reply_intent_prompt = """
You are an expert in understanding user intent. Take the following user message as input and determine which of the following cases it corresponds to.

### Output Format:
Provide the results in a JSON format following RFC8259, like this:
{{
  "intent": "<intent>"
}}

### Intent Values:
{intent}

### Task:
Analyze the following user message and determine the intent.

User Message: "{user_message}"

### Response:
Provide the response in JSON format with the appropriate intent value.
"""

human_needed_prompt = """
### Role and Task:
Write a text message to the user letting them know that you understand their request but as an AI you are not designed to handle this request, you will forward their request to a human agent

### Influencer Message:
{influencer_response}

### Output Format:

Provide the results in a JSON format following RFC8259, like this:
{{
  "message": "<message>",
}}
"""

paid_collaboration_response = """
Hi {lead_name}, <br>
        <p></p>
        Thank you so much for your response. I completely understand the 
importance of ensuring adequate compensation for your valuable work and 
influence. I truly respect your talent and the connection you have with your 
audience, which is why we reached out in the first place. <br>
        <p></p>
        I apologize, but at this time, we are unable to pre-pay for content before it 
is uploaded. Our company has invested heavily in developing cutting-edge 
technology to provide the most cost-effective and reliable products, which I 
believe is something you would want for your viewers as well. <br>
        <p></p>
        However, I would like to offer an alternative that I hope will be acceptable. 
We can execute a $94 per sell deal ($5 reservation + $84 final sale), a free 
machine(MSRP $599) is also included once 20 people are reserved through your 
link. Many influencers at your level have already been earning thousands of 
dollars in commission through our program. I believe this could be a great 
opportunity for you to earn a substantial amount while promoting a product that
aligns with your audience's interests. <br>
        <p></p>
        I hope we can find a way to collaborate that works for both parties. Please 
reply to this email if you're interested in this deal, and I'm happy to send over 
the details! <br>
        <p></p>
        Looking forward to your response. <br>
        <p></p>
        Best regards, <br>"""