import streamlit as st
import requests
import pandas as pd
import time

# API_URL = "https://eais-email-tmp.onrender.com"
API_URL = "http://localhost:8000"

# ---------------------------
# Utility functions
# ---------------------------
def create_campaign(api_url, campaign_name, uploaded_file, initial_email_template=""):
    """Create new campaign with file upload through API"""
    files = {
        "file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")
    }
    data = {
        "name": campaign_name,
        "initial_email_template": initial_email_template
    }
    
    try:
        response = requests.post(
            f"{api_url}/add_campaign/",
            data=data,
            files=files
        )
        return response
    except requests.exceptions.ConnectionError:
        return None

def generate_emails(api_url, campaign_id):
    """Trigger email generation through API"""
    return requests.post(
        f"{api_url}/generate_emails/",
        data={"campaign_id": campaign_id}
    )

def get_emails(api_url, campaign_id):
    """Retrieve generated emails from API"""
    return requests.get(f"{api_url}/campaign/get_emails/{campaign_id}")

def update_emails(api_url, campaign_id, emails):
    """Update email content through API"""
    return requests.post(
        f"{api_url}/campaign/update_emails/{campaign_id}",
        json=emails
    )

def send_emails(api_url, campaign_id):
    """Trigger email sending through API"""
    return requests.post(
        f"{api_url}/send_emails/",
        data={"campaign_id": campaign_id}
    )

# ---------------------------
# Streamlit UI
# ---------------------------
st.set_page_config(page_title="EAIS Email Campaign Manager", layout="wide")
st.title("Email Campaign Management")

# Session state initialization
if "campaign_id" not in st.session_state:
    st.session_state.campaign_id = None
if "emails_df" not in st.session_state:
    st.session_state.emails_df = None

# Sidebar navigation
page = st.sidebar.radio("Navigation", [
    "Create Campaign",
    "Generate Emails",
    "Edit Emails",
    "Send Campaign"
])

# ---------------------------
# Page: Create Campaign
# ---------------------------
if page == "Create Campaign":
    st.header("Create New Campaign")
    
    campaign_name = st.text_input("Campaign Name", "My Campaign")
    email_template = st.text_area("Base Email Template", "Hi {{full_name}},\n\n...")
    uploaded_file = st.file_uploader("Upload Leads CSV", type=["csv"])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.subheader("Leads Preview")
            st.dataframe(df.head(10))
        except Exception as e:
            st.error(f"Error reading CSV: {str(e)}")
    
    if st.button("Create Campaign") and uploaded_file:
        with st.spinner("Creating campaign..."):
            response = create_campaign(
                API_URL,
                campaign_name,
                uploaded_file,
                email_template
            )
            
        if response and response.status_code == 200:
            data = response.json()
            st.session_state.campaign_id = data["new_campaign_id"]
            st.success(f"Campaign created! ID: {st.session_state.campaign_id}")
            st.json(data["campaign"])
        else:
            error_msg = response.text if response else "API connection failed"
            st.error(f"Failed to create campaign: {error_msg}")

# ---------------------------
# Page: Generate & Edit Emails
# ---------------------------
elif page == "Generate Emails":
    st.header("Generate Emails")
    
    campaign_id = st.session_state.campaign_id
    if not campaign_id:
        st.warning("No campaign found in session. Please create a campaign first.")
    else:
        st.info(f"Working with campaign ID: {campaign_id}")

        if st.button("Generate Emails Now"):
            resp = generate_emails(API_URL, campaign_id)
            if resp.status_code == 200:
                max_retries = 30
                for attempt in range(max_retries):
                    emails_response = get_emails(API_URL, st.session_state.campaign_id)
                    if emails_response.status_code == 200:
                        st.session_state.emails_df = pd.DataFrame(emails_response.json()["emails"])
                        st.success("Emails generated successfully!")
                        break
                    # Wait before retrying
                    time.sleep(3)  # 3 seconds between attempts
                else:
                    st.error("Failed to retrieve emails after multiple attempts")
            else:
                st.error(f"API error: {resp.status_code} - {resp.text}")

elif page == "Edit Emails":
    st.header("Edit Emails")

    campaign_id = st.session_state.get("campaign_id", None)
    if not campaign_id:
        st.warning("No campaign found in session. Please create a campaign first.")
        st.stop()

    st.info(f"Working with campaign ID: {campaign_id}")

    if st.button("Fetch Emails"):
        resp = get_emails(API_URL, campaign_id)
        if resp.status_code == 200:
            st.session_state.emails_df = pd.DataFrame(resp.json()["emails"])
            st.success("Emails fetched successfully!")
        else:
            st.error(f"API error: {resp.status_code} - {resp.text}")

    # Display and edit
    if "emails_df" in st.session_state and not st.session_state.emails_df.empty:
        edited_emails = st.data_editor(st.session_state.emails_df)
        if st.button("Save Changes"):
            update_resp = update_emails(API_URL, campaign_id, edited_emails.to_dict("records"))
            if update_resp.status_code == 200:
                st.success("Emails updated successfully!")
            else:
                st.error(f"Update error: {update_resp.text}")

# ---------------------------
# Page: Send Campaign
# ---------------------------
elif page == "Send Campaign":
    st.header("Send Campaign Emails")
    
    if not st.session_state.campaign_id:
        st.warning("Please create a campaign first")
        st.stop()
    
    if st.button("Confirm & Send All Emails"):
        with st.spinner("Sending emails..."):
            response = send_emails(API_URL, st.session_state.campaign_id)
            
        if response.status_code == 200:
            st.success("Emails sent successfully!")
            st.balloons()
        else:
            st.error(f"Failed to send emails: {response.text}")