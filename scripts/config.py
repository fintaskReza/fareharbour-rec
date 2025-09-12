# Configuration and constants for the reconciliation app
import os

# Security configuration
ENABLE_VOID_FEATURE = os.getenv("ENABLE_VOID_FEATURE", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://n8n.fintask.ie/webhook/void_inv")
API_KEY = os.getenv("API_KEY", "")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_IRu7ADSfUxC6@ep-steep-star-af6ymzhg-pooler.c-2.us-west-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require")

# Page configuration
PAGE_CONFIG = {
    "page_title": "FareHarbour - QuickBooks Reconciliation",
    "page_icon": "📊",
    "layout": "wide",
    "initial_sidebar_state": "expanded"
}

# File paths for notes
NOTES_FILES = {
    "missing_bookings": "missing_bookings_notes.csv",
    "cancelled_vs_open": "cancelled_vs_open_notes.csv",
    "amount_differences": "reconciliation_notes.csv",
    "payment_refund": "payment_refund_notes.csv"
}

# Default password (should be changed in production)
DEFAULT_PASSWORD = "1234"
