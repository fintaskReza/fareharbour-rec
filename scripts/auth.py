# Authentication functions
import streamlit as st
import os
from scripts.config import DEFAULT_PASSWORD

def check_authentication():
    """Simple authentication check"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Authentication Required")
        st.warning("This application handles sensitive financial data. Please authenticate to continue.")

        # Check if password is set in environment or use default
        password = os.getenv("APP_PASSWORD", DEFAULT_PASSWORD)

        entered_password = st.text_input("Enter password:", type="password")

        if st.button("Login"):
            if entered_password == password:
                st.session_state.authenticated = True
                st.success("Authentication successful!")
                st.rerun()
            else:
                st.error("Invalid password")

        st.info("💡 For security, access is restricted. Contact your administrator for credentials.")
        st.stop()
