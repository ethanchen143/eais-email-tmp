import streamlit as st
import requests
import pandas as pd
import os

# ---------------------------
# Adjust these to match your FastAPI server
# ---------------------------
API_URL = "https://eais-email-api.onrender.com"

# ---------------------------
# Utility functions
# ---------------------------
def save_uploaded_file(uploaded_file):
    """
    Save uploaded file to a temporary folder, returning the path.
    """
    if uploaded_file is not None:
        # Make a 'tmp' folder if it doesn't exist
        if not os.path.exists("leads"):
            os.makedirs("leads")
        file_path = os.path.join("leads", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def create_campaign(api_base_url, campaign_name, leads_file_path, initial_email_template=""):
    """
    Hit the /add_campaign/ endpoint to create a new campaign on Instantly.
    """
    # We use multipart/form-data with Form fields for 'name', 'initial_email_template', and 'leads_file_path'.
    # Because your FastAPI code expects them as Form(...) parameters.
    data = {
        "name": campaign_name,
        "initial_email_template": initial_email_template,
        "leads_file_path": leads_file_path
    }
    response = requests.post(f"{api_base_url}/add_campaign/", data=data)
    return response

def generate_emails(api_base_url, campaign_id):
    """
    Hit the /generate_emails/ endpoint to generate the actual emails
    for each lead in the leads file.
    """
    data = {"campaign_id": campaign_id}
    response = requests.post(f"{api_base_url}/generate_emails/", data=data)
    return response

def send_emails(api_base_url, campaign_id):
    """
    Hit the /send_emails/ endpoint to actually send out all the emails.
    """
    data = {"campaign_id": campaign_id}
    response = requests.post(f"{api_base_url}/send_emails/", data=data)
    return response

# ---------------------------
# Streamlit layout
# ---------------------------
st.set_page_config(page_title="EAIS Email API", layout="wide")

st.title("EAIS Email API")

# We’ll use st.session_state to remember the campaign data across steps
if "campaign_id" not in st.session_state:
    st.session_state["campaign_id"] = None

if "campaign_info" not in st.session_state:
    st.session_state["campaign_info"] = None

# -------------
# Sidebar for steps
# -------------
page = st.sidebar.radio("Select a step", [
    "1. Upload & Create Campaign",
    "2. Generate Emails",
    "3. Preview / Edit Emails",
    "4. Send Emails"
])

# -------------
# STEP 1: Upload & Create Campaign
# -------------
if page == "1. Upload & Create Campaign":
    st.header("1. Upload Leads & Create New Campaign")

    # Campaign name
    campaign_name = st.text_input("Campaign Name", value="My New Campaign")

    # Initial email template (optional)
    template_text = st.text_area("Initial Email Template (optional)", 
                                 "Hi {{Full Name}},\n\nI noticed your profile...")

    # Upload the CSV file
    csv_file = st.file_uploader("Upload Leads CSV", type=["csv"])
    
    if csv_file is not None:
        # Just show a preview if you like:
        st.subheader("Preview of uploaded file")
        try:
            df_preview = pd.read_csv(csv_file)
            st.dataframe(df_preview.head(10))
        except Exception as e:
            st.error(f"Could not read CSV: {e}")

    if st.button("Create Campaign"):
        if not campaign_name.strip():
            st.error("Please enter a campaign name.")
        elif not csv_file:
            st.error("Please upload a leads CSV.")
        else:
            # Save the uploaded leads file locally
            saved_path = save_uploaded_file(csv_file)

            # Create the campaign by hitting your FastAPI endpoint
            resp = create_campaign(
                api_base_url=API_BASE_URL,
                campaign_name=campaign_name,
                leads_file_path=saved_path,  # pass local path
                initial_email_template=template_text
            )
            
            if resp.status_code == 200:
                resp_json = resp.json()
                if "new_campaign_id" in resp_json:
                    new_campaign_id = resp_json["new_campaign_id"]
                    st.session_state["campaign_id"] = new_campaign_id
                    st.session_state["campaign_info"] = resp_json.get("campaign")
                    st.success(
                        f"Campaign '{campaign_name}' created! Campaign ID: {new_campaign_id}"
                    )
                else:
                    st.error(f"Error creating campaign: {resp_json}")
            else:
                st.error(f"API error: {resp.status_code} - {resp.text}")

# -------------
# STEP 2: Generate Emails
# -------------
elif page == "2. Generate Emails":
    st.header("2. Generate Emails for your Campaign")
    
    campaign_id = st.session_state.get("campaign_id", None)
    if not campaign_id:
        st.warning("No campaign found in session. Please create a campaign first.")
    else:
        st.info(f"Working with campaign ID: {campaign_id}")

        if st.button("Generate Emails Now"):
            resp = generate_emails(API_BASE_URL, campaign_id)
            if resp.status_code == 200:
                resp_json = resp.json()
                if resp_json.get("status") == True:
                    st.success("Emails generated successfully!")
                else:
                    st.error("Failed to generate emails.")
                    st.write(resp_json)
            else:
                st.error(f"API error: {resp.status_code} - {resp.text}")

# -------------
# STEP 3: Preview / Edit Emails
# -------------
elif page == "3. Preview / Edit Emails":
    st.header("3. Preview & Edit Generated Emails")

    campaign_data = st.session_state.get("campaign_info", {})

    if not campaign_data:
        st.warning("No campaign_info in session. Create campaign & generate emails first.")
    else:
        campaign_id = campaign_data.get("campaign_id", "")
        if not campaign_id:
            st.warning("No campaign_id found in session. Please go back and generate emails first.")
        else:
            # Construct the file path
            generated_email_path = f"emails/generated_emails_{campaign_id}.csv"

            if not os.path.exists(generated_email_path):
                st.error(f"Generated email file not found at: {generated_email_path}")
            else:
                # Load and display the DataFrame
                df_emails = pd.read_csv(generated_email_path)
                st.subheader("Edit Generated Emails")
                st.write("Modify the `email_pitch` or other fields as needed:")

                # Allow editing of the DataFrame
                edited_df = st.data_editor(df_emails)

                # Save edits
                if st.button("Save Edits"):
                    try:
                        edited_df.to_csv(generated_email_path, index=False)
                        st.success("Edits saved successfully!")
                    except Exception as e:
                        st.error(f"Failed to save edits: {e}")

# -------------
# STEP 4: Send Emails
# -------------
elif page == "4. Send Emails":
    st.header("4. Send Emails")

    campaign_id = st.session_state.get("campaign_id", None)
    if not campaign_id:
        st.warning("No campaign found in session. Please create a campaign first.")
    else:
        st.info(f"Working with campaign ID: {campaign_id}")

        if st.button("Send Emails Now"):
            resp = send_emails(API_BASE_URL, campaign_id)
            if resp.status_code == 200:
                resp_json = resp.json()
                if resp_json.get("status") == True:
                    st.success("Emails sent successfully!")
                else:
                    st.error("Failed to send emails.")
                    st.write(resp_json)
            else:
                st.error(f"API error: {resp.status_code} - {resp.text}")