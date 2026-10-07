"""Web app entry point. Run with:  streamlit run app.py"""
import streamlit as st

from src import complaints, db

st.set_page_config(page_title="Pothole Detection System", page_icon=":material/warning:", layout="wide")
db.init_db()
complaints.init_db()

pages = st.navigation([
    st.Page("views/upload.py", title="Upload video", icon=":material/upload:"),
    st.Page("views/review.py", title="Review potholes", icon=":material/fact_check:"),
    st.Page("views/citizen_portal.py", title="Citizen portal", icon=":material/account_circle:", default=True),
    st.Page("views/bbmp_staff.py", title="BBMP staff", icon=":material/support_agent:"),
])
pages.run()
