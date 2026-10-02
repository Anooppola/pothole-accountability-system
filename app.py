"""Web app entry point. Run with:  streamlit run app.py"""
import streamlit as st

from src import db

st.set_page_config(page_title="Pothole Detection System", page_icon=":material/warning:", layout="wide")
db.init_db()

pages = st.navigation([
    st.Page("views/upload.py", title="Upload video", icon=":material/upload:", default=True),
    st.Page("views/review.py", title="Review potholes", icon=":material/fact_check:"),
])
pages.run()
