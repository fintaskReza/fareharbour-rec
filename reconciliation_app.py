import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import re
from io import BytesIO
import requests
import time
import os
import hashlib
import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Security configuration
ENABLE_VOID_FEATURE = os.getenv("ENABLE_VOID_FEATURE", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://n8n.fintask.ie/webhook/void_inv")
API_KEY = os.getenv("API_KEY", "")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_IRu7ADSfUxC6@ep-steep-star-af6ymzhg-pooler.c-2.us-west-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require")

@st.cache_resource
def get_database_connection():
    """Create and cache database connection"""
    try:
        engine = create_engine(DATABASE_URL)
        return engine
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

def execute_query(query, params=None):
    """Execute a database query and return results"""
    engine = get_database_connection()
    if engine is None:
        return None
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            if result.returns_rows:
                return result.fetchall()
            else:
                conn.commit()
                return True
    except SQLAlchemyError as e:
        st.error(f"Database error: {e}")
        return None

def check_authentication():
    """Simple authentication check"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        st.title("🔐 Authentication Required")
        st.warning("This application handles sensitive financial data. Please authenticate to continue.")
        
        # Check if password is set in environment or use default
        password = os.getenv("APP_PASSWORD", "fareharbour2024")
        
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

# Set page config
st.set_page_config(
    page_title="FareHarbour - QuickBooks Reconciliation",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Check authentication first
check_authentication()

def load_fareharbour_data(uploaded_file):
    """Load and clean FareHarbour CSV data"""
    try:
        # Reset file pointer to beginning
        uploaded_file.seek(0)
        
        # Read the CSV file
        df = pd.read_csv(uploaded_file)
        
        # Skip the first header row if it contains "Bookings"
        if len(df.columns) > 0 and (df.columns[0] == "Bookings" or str(df.columns[0]).strip() == "Bookings"):
            uploaded_file.seek(0)  # Reset file pointer
            df = pd.read_csv(uploaded_file, skiprows=1)
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Debug: Show available columns
        # st.write(f"Debug: Found {len(df.columns)} columns")
        # st.write("Available columns:", list(df.columns[:10]))  # Show first 10 columns
        # st.write(f"First column name: '{df.columns[0]}'")
        # st.write(f"First column equals 'Bookings': {df.columns[0] == 'Bookings'}")
        
        # Force skip first row if first column is "Bookings" (even if condition didn't work)
        if df.columns[0] == "Bookings":
            # st.write("DEBUG: Detected 'Bookings' header, re-reading with skiprows=1")
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, skiprows=1)
            df.columns = df.columns.str.strip()
            # st.write(f"After skipping: Found {len(df.columns)} columns")
            # st.write("New columns:", list(df.columns[:10]))
        
        # Check if required columns exist
        required_cols = ['Total Paid', 'Total', 'Booking ID', 'Cancelled?', 'Paid Status']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"Missing required columns: {missing_cols}")
            st.write("All available columns:", list(df.columns))
            return None
        
        # Convert key columns
        if 'Total Paid' in df.columns:
            df['Total Paid'] = pd.to_numeric(df['Total Paid'].str.replace('$', '').str.replace(',', ''), errors='coerce')
        if 'Total' in df.columns:
            df['Total'] = pd.to_numeric(df['Total'].str.replace('$', '').str.replace(',', ''), errors='coerce')
        
        # Convert tax and amount due columns for comparison
        if 'Total Tax' in df.columns:
            df['Total Tax'] = pd.to_numeric(df['Total Tax'].str.replace('$', '').str.replace(',', ''), errors='coerce')
        if 'Amount Due' in df.columns:
            df['Amount Due'] = pd.to_numeric(df['Amount Due'].str.replace('$', '').str.replace(',', ''), errors='coerce')
        
        # Extract booking ID without #
        if 'Booking ID' in df.columns:
            df['Booking ID Clean'] = df['Booking ID'].str.replace('#', '')
            
            # Debug: Show sample of FareHarbour booking IDs
            sample_raw_ids = df['Booking ID'].dropna().head(5).tolist()
            sample_clean_ids = df['Booking ID Clean'].dropna().head(5).tolist()
            # st.write("FH Debug: Sample raw booking IDs:", sample_raw_ids)
            # st.write("FH Debug: Sample clean booking IDs:", sample_clean_ids)
        
        # Convert dates
        if 'Created At Date' in df.columns:
            df['Created At Date'] = pd.to_datetime(df['Created At Date'], errors='coerce')
        if 'Start Date' in df.columns:
            df['Start Date'] = pd.to_datetime(df['Start Date'], errors='coerce')
        
        # Clean cancelled status
        if 'Cancelled?' in df.columns:
            # Check for both "Yes" and "Cancelled" values
            cancelled_values = df['Cancelled?'].str.lower().str.strip()
            df['Is Cancelled'] = cancelled_values.isin(['yes', 'cancelled'])
        else:
            st.warning("'Cancelled?' column not found in uploaded file!")
        if 'Paid Status' in df.columns:
            df['Is Paid'] = df['Paid Status'].str.lower().str.strip() == 'paid'
        
        st.success(f"Successfully loaded {len(df)} FareHarbour bookings")
        return df
    except Exception as e:
        st.error(f"Error loading FareHarbour data: {str(e)}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None

def load_fareharbour_payments_data(uploaded_file):
    """Load and clean FareHarbour payments/refunds CSV data"""
    try:
        # Reset file pointer to beginning
        uploaded_file.seek(0)
        
        # Read the CSV file
        df = pd.read_csv(uploaded_file)
        
        # Skip the first header row if it contains "Sales" and "Bookings"
        if len(df.columns) > 0 and ("Sales" in str(df.columns[0]) or "Bookings" in str(df.iloc[0]).join(str(df.columns))):
            uploaded_file.seek(0)  # Reset file pointer
            df = pd.read_csv(uploaded_file, skiprows=1)
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Check if required columns exist
        required_cols = ['Payment or Refund', 'Booking ID', 'Gross', 'Net']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"Missing required columns in payments data: {missing_cols}")
            st.write("All available columns:", list(df.columns))
            return None
        
        # Convert amount columns to numeric
        amount_columns = [
            'Gross', 'Processing Fee', 'Net',
            'Payment Gross', 'Payment Processing Fee', 'Payment Net',
            'Refund Gross', 'Refund Processing Fee', 'Refund Net',
            'Subtotal Paid', 'Dashboard Tax Rate (5%) Paid', 'Tax Paid'
        ]
        
        for col in amount_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace('$', '').str.replace(',', ''), 
                    errors='coerce'
                )
        
        # Extract booking ID without #
        if 'Booking ID' in df.columns:
            df['Booking ID Clean'] = df['Booking ID'].astype(str).str.replace('#', '')
        
        # Convert dates
        date_columns = ['Created At Date', 'Created At']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Create payment/refund flags
        if 'Payment or Refund' in df.columns:
            df['Is Payment'] = df['Payment or Refund'].str.lower().str.strip() == 'payment'
            df['Is Refund'] = df['Payment or Refund'].str.lower().str.strip() == 'refund'
        
        # Handle cancelled status if present
        if 'Cancelled?' in df.columns:
            cancelled_values = df['Cancelled?'].str.lower().str.strip()
            df['Is Cancelled'] = cancelled_values.isin(['yes', 'cancelled'])
        
        st.success(f"Successfully loaded {len(df)} FareHarbour payment/refund transactions")
        
        # Show summary
        if 'Is Payment' in df.columns and 'Is Refund' in df.columns:
            payment_count = df['Is Payment'].sum()
            refund_count = df['Is Refund'].sum()
            st.info(f"Found {payment_count} payments and {refund_count} refunds")
        
        return df
    except Exception as e:
        st.error(f"Error loading FareHarbour payments data: {str(e)}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None

def load_quickbooks_data(uploaded_file):
    """Load and clean QuickBooks Excel data"""
    try:
        # Read the Excel file to examine structure
        temp_df = pd.read_excel(uploaded_file)
        
        # Based on the image, the structure appears to be:
        # Row 0: "Maaqutusiis Hahoulthee Enterprises Inc."
        # Row 1: "Transaction List by Date"  
        # Row 2: "June 17 - July 8, 2025"
        # Row 3: Empty or column headers
        # Row 4: Actual column headers with Date, #, Posting, etc.
        
        # Based on analysis, the data starts at row 4 (index 3), but headers are at that row
        # The structure is: Empty col, Date, #, Posting, Name, Memo/Description, Account, Split, Amount, etc.
        df = pd.read_excel(uploaded_file, header=3)
        
        # The first column is empty, so drop it and use row 0 as headers
        df = df.drop(df.columns[0], axis=1)  # Drop the first unnamed column
        
        # Set the column names from the first row of data
        new_columns = df.iloc[0].tolist()  # Get the first row as column names
        df.columns = new_columns
        df = df.drop(df.index[0])  # Remove the header row from data
        df.reset_index(drop=True, inplace=True)
        
        # Clean column names
        df.columns = [str(col).strip() if pd.notna(col) else f'Unknown_{i}' for i, col in enumerate(df.columns)]
        
        # Drop completely empty rows
        df = df.dropna(how='all')
        
        # Based on the image, map columns more accurately
        # The columns appear to be: Date, #, Posting, Name, Memo/Description, Account, Split, Amount, Tax Amount, Create Date, Ref #, FH booking ID, Invoice Date, Open Balance, Payment Method, Net Amount
        
        # Extract FH booking ID from multiple possible columns
        def extract_fh_id(row):
            # PRIORITY 1: Check the dedicated "FH booking ID" column first (contains clean numeric IDs)
            fh_id_columns = ['FH booking ID', 'FH_booking_ID', 'FH_Booking_ID_Column']
            for col in fh_id_columns:
                if col in df.columns:
                    fh_id_val = row.get(col)
                    if pd.notna(fh_id_val) and str(fh_id_val).strip():
                        # Return the clean numeric ID from the dedicated column
                        return str(fh_id_val).strip()
            
            # PRIORITY 2: Check the # column for various ID formats
            if '#' in df.columns:
                num_col_val = row.get('#')
                if pd.notna(num_col_val):
                    val_str = str(num_col_val).strip()
                    # If it's an FH- code, return as is (for reference, but these won't match FH numeric IDs)
                    if 'FH-' in val_str:
                        return val_str
                    # If it's a numeric booking ID with #, extract the number
                    if val_str.startswith('#') and val_str[1:].isdigit():
                        return val_str[1:]  # Remove the # to get clean number
            
            # PRIORITY 3: Check all other columns for FH booking ID patterns as fallback
            for col_name, val in row.items():
                if col_name in ['#'] + fh_id_columns:
                    continue  # Already checked these
                    
                val_str = str(val) if pd.notna(val) else ''
                
                # Look for FH- pattern
                if 'FH-' in val_str:
                    return val_str.strip()
                
                # Look for booking ID pattern like #290981542
                match = re.search(r'#(\d{8,})', val_str)
                if match:
                    return match.group(1)  # Return just the numeric part
                    
            return None
        
        df['FH_Booking_ID'] = df.apply(extract_fh_id, axis=1)
        
        # Debug: Show QuickBooks columns and extracted IDs
        # st.write(f"QB Debug: Found {len(df.columns)} columns")
        # st.write("QB Available columns:", list(df.columns))
        
        # Debug: Show sample of extracted FH booking IDs
        extracted_ids = df['FH_Booking_ID'].dropna()
        # st.write(f"QB Debug: Extracted {len(extracted_ids)} FH booking IDs")
        if len(extracted_ids) > 0:
            sample_ids = extracted_ids.head(10).tolist()
            # st.write("QB Debug: Sample FH booking IDs:", sample_ids)
            
            # Show breakdown by type
            fh_codes = [id for id in extracted_ids if str(id).startswith('FH-')]
            numeric_ids = [id for id in extracted_ids if not str(id).startswith('FH-') and str(id).isdigit()]
            # st.write(f"QB Debug: FH-codes: {len(fh_codes)}, Numeric IDs: {len(numeric_ids)}")
            
            if len(numeric_ids) > 0:
                pass
                # st.write("QB Debug: Sample numeric IDs:", numeric_ids[:5])
        
        # Check specifically for the "FH booking ID" column
        fh_booking_col = 'FH_Booking_ID_Column' if 'FH_Booking_ID_Column' in df.columns else None
        if not fh_booking_col:
            fh_booking_col = 'FH booking ID' if 'FH booking ID' in df.columns else None
        
        if fh_booking_col:
            fh_col_data = df[fh_booking_col].dropna()
            # st.write(f"QB Debug: Found dedicated FH booking ID column '{fh_booking_col}' with {len(fh_col_data)} values")
            if len(fh_col_data) > 0:
                pass
                # st.write("QB Debug: Sample values from FH booking ID column:", fh_col_data.head(5).tolist())
        # else:
            # st.warning("QB Debug: No dedicated 'FH booking ID' column found!")
        
        # Convert amount and balance columns to numeric
        amount_columns = ['Amount', 'Net Amount', 'Open Balance', 'Tax Amount']
        for col in amount_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Convert date columns
        date_columns = ['Date', 'Create Date', 'Invoice Date']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Standardize column names for easier access
        column_mapping = {
            'Net Amount': 'Net_Amount',
            'Open Balance': 'Open_Balance',
            'Tax Amount': 'Tax_Amount',
            'Create Date': 'Create_Date',
            'Invoice Date': 'Invoice_Date',
            'FH booking ID': 'FH_Booking_ID_Column'
        }
        
        # Apply column mapping
        df = df.rename(columns=column_mapping)
        
        return df
    except Exception as e:
        st.error(f"Error loading QuickBooks data: {str(e)}")
        return None

def find_missing_bookings(fh_df, qb_df):
    """Find bookings in FH that are missing in QB"""
    if fh_df is None or qb_df is None:
        return pd.DataFrame()
    
    # Get FareHarbour booking IDs (should be clean numeric IDs)
    fh_booking_ids = set(fh_df['Booking ID Clean'].dropna().astype(str))
    
    # Get QuickBooks booking IDs, filtering out FH-codes and keeping only numeric IDs
    qb_numeric_ids = set()
    for qb_id in qb_df['FH_Booking_ID'].dropna():
        qb_id_str = str(qb_id).strip()
        # Only include numeric booking IDs, not FH-codes
        if not qb_id_str.startswith('FH-') and qb_id_str.isdigit():
            qb_numeric_ids.add(qb_id_str)
    

    
    missing_ids = fh_booking_ids - qb_numeric_ids
    
    missing_bookings = fh_df[fh_df['Booking ID Clean'].astype(str).isin(missing_ids)].copy()
    return missing_bookings

def find_cancelled_vs_open(fh_df, qb_df):
    """Find bookings that are cancelled in FH but have open invoices in QB"""
    if fh_df is None or qb_df is None:
        return pd.DataFrame()
    
    # Get cancelled bookings from FH with additional context
    cancelled_fh_data = fh_df[fh_df['Is Cancelled'] == True].copy()
    cancelled_fh_ids = cancelled_fh_data['Booking ID Clean'].astype(str).tolist()
    
    # Filter QB data to only include numeric booking IDs that match our cancelled FH bookings
    qb_with_numeric_ids = qb_df[
        qb_df['FH_Booking_ID'].notna() & 
        ~qb_df['FH_Booking_ID'].astype(str).str.startswith('FH-') &
        qb_df['FH_Booking_ID'].astype(str).str.isdigit() &
        qb_df['FH_Booking_ID'].astype(str).isin(cancelled_fh_ids)
    ].copy()
    
    # Check if Open_Balance column exists, if not, use alternative logic
    if 'Open_Balance' not in qb_df.columns:
        st.warning("Open_Balance column not found in QuickBooks data. Using FH booking ID matches only.")
        cancelled_with_open = qb_with_numeric_ids
    else:
        # Find these in QB with open balances
        cancelled_with_open = qb_with_numeric_ids[qb_with_numeric_ids['Open_Balance'] > 0].copy()
    
    # If we found matches, merge with FH data to add context like Created At Date
    if not cancelled_with_open.empty and not cancelled_fh_data.empty:
        # Prepare FH data for merge (include useful context columns)
        fh_context_cols = ['Booking ID Clean', 'Contact', 'Item', 'Created At Date', 'Start Date', 'Total', 'Cancelled?']
        available_fh_cols = [col for col in fh_context_cols if col in cancelled_fh_data.columns]
        fh_for_merge = cancelled_fh_data[available_fh_cols].copy()
        fh_for_merge['Booking ID Clean'] = fh_for_merge['Booking ID Clean'].astype(str)
        
        # Convert QB booking ID to string for merge
        cancelled_with_open['FH_Booking_ID'] = cancelled_with_open['FH_Booking_ID'].astype(str)
        
        # Merge to add FH context
        result = pd.merge(
            fh_for_merge,
            cancelled_with_open,
            left_on='Booking ID Clean',
            right_on='FH_Booking_ID',
            how='inner'
        )
        return result
    
    return cancelled_with_open

def compare_amounts(fh_df, qb_df):
    """Compare amounts between matching bookings using proper FH vs QB columns"""
    if fh_df is None or qb_df is None:
        return pd.DataFrame()
    
    # Define required FH columns for comparison
    fh_required_cols = ['Booking ID Clean', 'Total', 'Total Tax', 'Amount Due', 'Is Paid', 'Is Cancelled']
    fh_missing_cols = [col for col in fh_required_cols if col not in fh_df.columns]
    
    # Define required QB columns for comparison  
    qb_required_cols = ['FH_Booking_ID', 'Amount', 'Tax_Amount', 'Open_Balance']
    qb_missing_cols = [col for col in qb_required_cols if col not in qb_df.columns]
    
    # Handle missing columns with warnings
    if fh_missing_cols:
        st.warning(f"FareHarbour missing columns for comparison: {fh_missing_cols}")
        # Use fallback columns where possible
        fh_cols = ['Booking ID Clean', 'Is Paid', 'Is Cancelled']
        # Always try to include Created At Date for context
        if 'Created At Date' in fh_df.columns:
            fh_cols.append('Created At Date')
        if 'Total' in fh_df.columns:
            fh_cols.append('Total')
        if 'Total Paid' in fh_df.columns:
            fh_cols.append('Total Paid')
            if 'Total' not in fh_df.columns:
                st.info("Using 'Total Paid' instead of 'Total' for FareHarbour")
            else:
                st.info("Including both 'Total' and 'Total Paid' columns for comparison")
        if 'Total Tax' in fh_df.columns:
            fh_cols.append('Total Tax')
        if 'Amount Due' in fh_df.columns:
            fh_cols.append('Amount Due')
    else:
        fh_cols = fh_required_cols.copy()
        # Always try to include Created At Date for context
        if 'Created At Date' in fh_df.columns:
            fh_cols.append('Created At Date')
        # Always include Total Paid if available (needed for cancellation logic)
        if 'Total Paid' in fh_df.columns:
            fh_cols.append('Total Paid')
            st.info("Including 'Total Paid' column for payment status analysis")
    
    if qb_missing_cols:
        st.warning(f"QuickBooks missing columns for comparison: {qb_missing_cols}")
        qb_cols = ['FH_Booking_ID']
        if 'Amount' in qb_df.columns:
            qb_cols.append('Amount')
        if 'Tax_Amount' in qb_df.columns:
            qb_cols.append('Tax_Amount')
        elif 'Tax Amount' in qb_df.columns:
            qb_cols.append('Tax Amount')
            st.info("Using 'Tax Amount' instead of 'Tax_Amount' for QuickBooks")
        if 'Open_Balance' in qb_df.columns:
            qb_cols.append('Open_Balance')
        elif 'Open Balance' in qb_df.columns:
            qb_cols.append('Open Balance')
            st.info("Using 'Open Balance' instead of 'Open_Balance' for QuickBooks")
    else:
        qb_cols = qb_required_cols
    
    # Prepare FH data with string booking IDs for consistent comparison
    fh_merge_df = fh_df[fh_cols].copy()
    fh_merge_df['Booking ID Clean'] = fh_merge_df['Booking ID Clean'].astype(str)
    
    # Prepare QB data - only include numeric booking IDs
    qb_merge_df = qb_df[qb_cols].copy()
    qb_merge_df = qb_merge_df[
        qb_merge_df['FH_Booking_ID'].notna() & 
        ~qb_merge_df['FH_Booking_ID'].astype(str).str.startswith('FH-') &
        qb_merge_df['FH_Booking_ID'].astype(str).str.isdigit()
    ]
    qb_merge_df['FH_Booking_ID'] = qb_merge_df['FH_Booking_ID'].astype(str)
    
    # Convert QB amount columns to numeric before aggregation
    qb_amount_cols = [col for col in qb_cols if col != 'FH_Booking_ID']
    for col in qb_amount_cols:
        if col in qb_merge_df.columns:
            qb_merge_df[col] = pd.to_numeric(qb_merge_df[col], errors='coerce')
    
    # Handle refunds by aggregating QB transactions per booking ID
    # This handles cases where there's an original transaction + refund transaction
    if len(qb_merge_df) > 0:
        # Group by booking ID and sum amounts (original + refund = net amount)
        agg_dict = {'FH_Booking_ID': 'first'}  # Keep the booking ID
        for col in qb_amount_cols:
            if col in qb_merge_df.columns:
                agg_dict[col] = 'sum'  # Sum all transactions for same booking ID
        
        qb_merge_df = qb_merge_df.groupby('FH_Booking_ID').agg(agg_dict).reset_index(drop=True)
        

    else:
        st.warning("No QB data with numeric booking IDs found for comparison.")
    
    # Merge on booking ID
    merged = pd.merge(
        fh_merge_df,
        qb_merge_df,
        left_on='Booking ID Clean',
        right_on='FH_Booking_ID',
        how='inner'
    )
    
    if merged.empty:
        st.warning("No matching bookings found between FareHarbour and QuickBooks for comparison.")
        return pd.DataFrame()
    
    # Rename columns for clarity
    column_renames = {
        'Booking ID Clean': 'Booking_ID',
        'Total': 'FH_Total_Amount',
        'Total Paid': 'FH_Total_Paid',  # Different name to avoid duplicates
        'Total Tax': 'FH_Total_Tax',
        'Amount Due': 'FH_Amount_Due',
        'Is Paid': 'FH_Is_Paid',
        'Is Cancelled': 'FH_Is_Cancelled',
        'Amount': 'QB_Amount',
        'Tax_Amount': 'QB_Tax_Amount',
        'Tax Amount': 'QB_Tax_Amount',  # Alternative naming
        'Open_Balance': 'QB_Open_Balance',
        'Open Balance': 'QB_Open_Balance'  # Alternative naming
    }
    
    # Apply renames only for columns that exist
    renames_to_apply = {old: new for old, new in column_renames.items() if old in merged.columns}
    merged = merged.rename(columns=renames_to_apply)
    
    # Ensure all amount columns are numeric before calculations
    amount_cols_to_convert = ['FH_Total_Amount', 'FH_Total_Paid', 'FH_Total_Tax', 'FH_Amount_Due', 'QB_Amount', 'QB_Tax_Amount', 'QB_Open_Balance']
    
    for col in amount_cols_to_convert:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors='coerce')
    
    # For cancelled bookings, handle amounts based on payment status
    # Only set amounts to 0 if cancelled AND paid amount is null/0
    if 'FH_Is_Cancelled' in merged.columns:
        cancelled_count = merged['FH_Is_Cancelled'].sum()
        
        if 'FH_Total_Paid' in merged.columns:
            # Only set amounts to 0 for cancelled bookings with null/0 paid amount
            cancelled_with_no_payment = (merged['FH_Is_Cancelled']) & (merged['FH_Total_Paid'].fillna(0) == 0)
            cancelled_with_payment = (merged['FH_Is_Cancelled']) & (merged['FH_Total_Paid'].fillna(0) > 0)
            
            if 'FH_Total_Amount' in merged.columns:
                # For cancelled bookings with payment, use the paid amount as the total for comparison
                merged.loc[cancelled_with_payment, 'FH_Total_Amount'] = merged.loc[cancelled_with_payment, 'FH_Total_Paid']
                
                # Only set total to 0 for cancelled bookings with no payment
                merged.loc[cancelled_with_no_payment, 'FH_Total_Amount'] = 0
            
            # Only set FH_Total_Paid to 0 for cancelled bookings with no payment (for consistency in display)
            merged.loc[cancelled_with_no_payment, 'FH_Total_Paid'] = 0
            
        elif 'FH_Total_Amount' in merged.columns:
            # For cancelled bookings, assume they should be 0 if Amount Due equals Total (unpaid)
            if 'FH_Amount_Due' in merged.columns:
                # If Amount Due equals Total, it means the booking is unpaid
                cancelled_unpaid = (merged['FH_Is_Cancelled']) & (abs(merged['FH_Amount_Due'] - merged['FH_Total_Amount']) < 0.01)
                merged.loc[cancelled_unpaid, 'FH_Total_Amount'] = 0
            else:
                # If no Amount Due column, assume all cancelled bookings should be 0
                merged.loc[merged['FH_Is_Cancelled'], 'FH_Total_Amount'] = 0
        
        # Handle tax amounts for cancelled bookings - only zero out if no payment
        if 'FH_Total_Tax' in merged.columns:
            # Only zero tax for cancelled bookings with no payment
            if 'FH_Total_Paid' in merged.columns:
                cancelled_with_no_payment = (merged['FH_Is_Cancelled']) & (merged['FH_Total_Paid'].fillna(0) == 0)
                merged.loc[cancelled_with_no_payment, 'FH_Total_Tax'] = 0
            # If we can't determine payment status, leave tax as-is for cancelled bookings
        
        # Handle Amount Due - this should typically be 0 for cancelled bookings regardless of payment
        if 'FH_Amount_Due' in merged.columns:
            merged.loc[merged['FH_Is_Cancelled'], 'FH_Amount_Due'] = 0
    else:
        st.error("'FH_Is_Cancelled' column not found in merged data!")
    
    # Calculate amount differences with clear labeling
    differences_found = []
    
    # Compare total amounts: FH Total vs QB Amount  
    if 'FH_Total_Amount' in merged.columns and 'QB_Amount' in merged.columns:
        merged['Total_Amount_Difference'] = merged['FH_Total_Amount'].fillna(0) - merged['QB_Amount'].fillna(0)
        merged['Has_Total_Difference'] = abs(merged['Total_Amount_Difference']) > 0.01
        differences_found.append('Total_Amount_Difference')
    
    # Compare tax amounts: FH Total Tax vs QB Tax Amount
    if 'FH_Total_Tax' in merged.columns and 'QB_Tax_Amount' in merged.columns:
        merged['Tax_Amount_Difference'] = merged['FH_Total_Tax'].fillna(0) - merged['QB_Tax_Amount'].fillna(0)
        merged['Has_Tax_Difference'] = abs(merged['Tax_Amount_Difference']) > 0.01
        differences_found.append('Tax_Amount_Difference')
    
    # Compare payment status: FH Amount Due vs QB Open Balance
    if 'FH_Amount_Due' in merged.columns and 'QB_Open_Balance' in merged.columns:
        merged['Payment_Status_Difference'] = merged['FH_Amount_Due'].fillna(0) - merged['QB_Open_Balance'].fillna(0)
        merged['Has_Payment_Difference'] = abs(merged['Payment_Status_Difference']) > 0.01
        differences_found.append('Payment_Status_Difference')
    
    # Filter to only rows with differences
    if differences_found:
        diff_conditions = []
        
        # Check each type of difference
        if 'Has_Total_Difference' in merged.columns:
            diff_conditions.append(merged['Has_Total_Difference'])
        if 'Has_Tax_Difference' in merged.columns:
            diff_conditions.append(merged['Has_Tax_Difference'])
        if 'Has_Payment_Difference' in merged.columns:
            diff_conditions.append(merged['Has_Payment_Difference'])
        
        if diff_conditions:
            # Combine all difference conditions with OR
            has_any_difference = diff_conditions[0]
            for condition in diff_conditions[1:]:
                has_any_difference = has_any_difference | condition
            
            result = merged[has_any_difference].copy()
        else:
            result = pd.DataFrame()
    else:
        st.warning("No comparable amount columns found between FareHarbour and QuickBooks.")
        result = pd.DataFrame()
    
    return result

def compare_payments_refunds(fh_payments_df, qb_df):
    """Compare payments and refunds between FareHarbour and QuickBooks"""
    if fh_payments_df is None or qb_df is None:
        return pd.DataFrame()
    
    # Prepare FareHarbour payments data by grouping by booking ID
    fh_summary = fh_payments_df.groupby('Booking ID Clean').agg({
        'Gross': ['sum'],
        'Net': ['sum'],
        'Processing Fee': ['sum'],
        'Payment Gross': ['sum', 'count'],
        'Payment Net': ['sum'],
        'Payment Processing Fee': ['sum'],
        'Refund Gross': ['sum', 'count'],
        'Refund Net': ['sum'],
        'Refund Processing Fee': ['sum'],
        'Tax Paid': ['sum'],
        'Is Payment': ['sum'],
        'Is Refund': ['sum'],
        'Created At Date': ['min', 'max']  # Date range for this booking
    }).reset_index()
    
    # Flatten column names
    fh_summary.columns = [
        'Booking_ID',
        'FH_Total_Gross', 'FH_Total_Net', 'FH_Total_Processing_Fee',
        'FH_Payment_Gross', 'FH_Payment_Count', 'FH_Payment_Net', 'FH_Payment_Processing_Fee',
        'FH_Refund_Gross', 'FH_Refund_Count', 'FH_Refund_Net', 'FH_Refund_Processing_Fee',
        'FH_Tax_Paid', 'FH_Payment_Transactions', 'FH_Refund_Transactions',
        'FH_First_Transaction_Date', 'FH_Last_Transaction_Date'
    ]
    
    # Calculate total activity (sum of all payments + refunds)
    fh_summary['FH_Total_Activity'] = fh_summary['FH_Payment_Gross'].fillna(0) + fh_summary['FH_Refund_Gross'].fillna(0)
    fh_summary['FH_Net_Amount'] = fh_summary['FH_Payment_Net'].fillna(0) - fh_summary['FH_Refund_Net'].fillna(0)
    fh_summary['FH_Net_Processing_Fee'] = fh_summary['FH_Payment_Processing_Fee'].fillna(0) - fh_summary['FH_Refund_Processing_Fee'].fillna(0)
    
    # Convert booking ID to string for consistent comparison
    fh_summary['Booking_ID'] = fh_summary['Booking_ID'].astype(str)
    
    # Prepare QuickBooks data - aggregate by booking ID
    qb_with_fh_ids = qb_df[
        qb_df['FH_Booking_ID'].notna() & 
        ~qb_df['FH_Booking_ID'].astype(str).str.startswith('FH-') &
        qb_df['FH_Booking_ID'].astype(str).str.isdigit()
    ].copy()
    
    if qb_with_fh_ids.empty:
        st.warning("No QuickBooks transactions with numeric FareHarbour booking IDs found for payment comparison.")
        return pd.DataFrame()
    
    qb_with_fh_ids['FH_Booking_ID'] = qb_with_fh_ids['FH_Booking_ID'].astype(str)
    
    # Convert QB amount columns to numeric
    qb_amount_cols = ['Amount', 'Net_Amount', 'Tax_Amount', 'Open_Balance']
    for col in qb_amount_cols:
        if col in qb_with_fh_ids.columns:
            qb_with_fh_ids[col] = pd.to_numeric(qb_with_fh_ids[col], errors='coerce')
    
    # Aggregate QB data by booking ID
    # Note: In QB, positive amounts are typically payments, negative amounts are refunds
    qb_agg_dict = {
        'FH_Booking_ID': 'first'
    }
    
    if 'Amount' in qb_with_fh_ids.columns:
        # Separate positive (payments) and negative (refunds) amounts
        qb_with_fh_ids['QB_Payment_Amount'] = qb_with_fh_ids['Amount'].where(qb_with_fh_ids['Amount'] > 0, 0)
        qb_with_fh_ids['QB_Refund_Amount'] = qb_with_fh_ids['Amount'].where(qb_with_fh_ids['Amount'] < 0, 0).abs()
        
        # Calculate total activity (sum of absolute values of all transactions)
        qb_with_fh_ids['QB_Total_Activity'] = qb_with_fh_ids['QB_Payment_Amount'] + qb_with_fh_ids['QB_Refund_Amount']
        
        qb_agg_dict['Amount'] = 'sum'  # Net amount (payments - refunds)
        qb_agg_dict['QB_Payment_Amount'] = 'sum'
        qb_agg_dict['QB_Refund_Amount'] = 'sum'
        qb_agg_dict['QB_Total_Activity'] = 'sum'
    
    if 'Net_Amount' in qb_with_fh_ids.columns:
        qb_agg_dict['Net_Amount'] = 'sum'
    
    if 'Tax_Amount' in qb_with_fh_ids.columns:
        qb_agg_dict['Tax_Amount'] = 'sum'
    
    if 'Open_Balance' in qb_with_fh_ids.columns:
        qb_agg_dict['Open_Balance'] = 'sum'
    
    # Add date columns for min/max aggregation
    if 'Date' in qb_with_fh_ids.columns:
        qb_with_fh_ids['Date_min'] = qb_with_fh_ids['Date']
        qb_with_fh_ids['Date_max'] = qb_with_fh_ids['Date']
        qb_agg_dict['Date_min'] = 'min'
        qb_agg_dict['Date_max'] = 'max'
    
    # Add transaction count using a dummy column
    qb_with_fh_ids['_count'] = 1
    qb_agg_dict['_count'] = 'sum'
    
    qb_summary = qb_with_fh_ids.groupby('FH_Booking_ID').agg(qb_agg_dict).reset_index(drop=True)
    
    # Flatten QB column names
    new_qb_cols = ['Booking_ID']
    for col in qb_summary.columns[1:]:
        if isinstance(col, tuple):
            if col[1] == 'first':
                new_qb_cols.append(f'QB_{col[0]}')
            elif col[1] in ['min', 'max']:
                new_qb_cols.append(f'QB_{col[0]}_{col[1]}')
            else:
                new_qb_cols.append(f'QB_{col[0]}_{col[1]}')
        else:
            new_qb_cols.append(f'QB_{col}')
    
    qb_summary.columns = new_qb_cols
    
    # Rename specific columns for clarity
    column_renames = {
        'QB_FH_Booking_ID': 'Booking_ID',
        'QB_Amount_sum': 'QB_Net_Amount',
        'QB_Net_Amount_sum': 'QB_Net_Amount_Alt',
        'QB_Tax_Amount_sum': 'QB_Tax_Amount',
        'QB_Open_Balance_sum': 'QB_Open_Balance',
        'QB_QB_Payment_Amount_sum': 'QB_Payment_Amount',
        'QB_QB_Refund_Amount_sum': 'QB_Refund_Amount',
        'QB_QB_Total_Activity_sum': 'QB_Total_Activity',
        'QB__count_sum': 'QB_Transaction_Count',
        'QB_Date_min_min': 'QB_First_Transaction_Date',
        'QB_Date_max_max': 'QB_Last_Transaction_Date'
    }
    
    for old_col, new_col in column_renames.items():
        if old_col in qb_summary.columns:
            qb_summary = qb_summary.rename(columns={old_col: new_col})
    
    # Merge FareHarbour and QuickBooks data
    merged = pd.merge(
        fh_summary,
        qb_summary,
        on='Booking_ID',
        how='inner'
    )
    
    if merged.empty:
        st.warning("No matching booking IDs found between FareHarbour payments and QuickBooks for comparison.")
        return pd.DataFrame()
    
    # Calculate differences and identify missing transactions
    # Total activity comparison (sum of all payments + refunds)
    if 'QB_Total_Activity' in merged.columns:
        merged['Total_Activity_Difference'] = merged['FH_Total_Activity'].fillna(0) - merged['QB_Total_Activity'].fillna(0)
        merged['Has_Activity_Difference'] = abs(merged['Total_Activity_Difference']) > 0.01
    
    # Payment amount difference - compare FH gross to QB amounts
    if 'QB_Payment_Amount' in merged.columns:
        merged['Payment_Amount_Difference'] = merged['FH_Payment_Gross'].fillna(0) - merged['QB_Payment_Amount'].fillna(0)
        merged['Has_Payment_Difference'] = abs(merged['Payment_Amount_Difference']) > 0.01
    
    # Refund amount difference - compare FH gross to QB amounts
    if 'QB_Refund_Amount' in merged.columns:
        merged['Refund_Amount_Difference'] = merged['FH_Refund_Gross'].fillna(0) - merged['QB_Refund_Amount'].fillna(0)
        merged['Has_Refund_Difference'] = abs(merged['Refund_Amount_Difference']) > 0.01
    
    # Add logic to identify missing payments or refunds
    merged['Missing_Transaction_Type'] = 'None'
    
    # Initialize boolean masks
    missing_payments = pd.Series([False] * len(merged), index=merged.index)
    missing_refunds = pd.Series([False] * len(merged), index=merged.index)
    
    # If FH has payments but QB doesn't (or has less)
    if 'QB_Payment_Amount' in merged.columns and 'Payment_Amount_Difference' in merged.columns:
        missing_payments = (merged['FH_Payment_Gross'].fillna(0) > 0) & (merged['Payment_Amount_Difference'] > 0.01)
        merged.loc[missing_payments, 'Missing_Transaction_Type'] = 'Missing Payment in QB'
    
    # If FH has refunds but QB doesn't (or has less)
    if 'QB_Refund_Amount' in merged.columns and 'Refund_Amount_Difference' in merged.columns:
        missing_refunds = (merged['FH_Refund_Gross'].fillna(0) > 0) & (merged['Refund_Amount_Difference'] > 0.01)
        merged.loc[missing_refunds, 'Missing_Transaction_Type'] = 'Missing Refund in QB'
    
    # If both payments and refunds are missing
    if ('QB_Payment_Amount' in merged.columns and 'QB_Refund_Amount' in merged.columns and 
        'Payment_Amount_Difference' in merged.columns and 'Refund_Amount_Difference' in merged.columns):
        missing_both = missing_payments & missing_refunds
        merged.loc[missing_both, 'Missing_Transaction_Type'] = 'Missing Payment & Refund in QB'
    
    # If QB has more than FH (unexpected extra transactions in QB)
    if 'QB_Payment_Amount' in merged.columns and 'Payment_Amount_Difference' in merged.columns:
        extra_payments = merged['Payment_Amount_Difference'] < -0.01
        merged.loc[extra_payments, 'Missing_Transaction_Type'] = 'Extra Payment in QB'
    
    if 'QB_Refund_Amount' in merged.columns and 'Refund_Amount_Difference' in merged.columns:
        extra_refunds = merged['Refund_Amount_Difference'] < -0.01
        merged.loc[extra_refunds, 'Missing_Transaction_Type'] = 'Extra Refund in QB'
    
    # Tax difference
    if 'QB_Tax_Amount' in merged.columns:
        merged['Tax_Difference'] = merged['FH_Tax_Paid'].fillna(0) - merged['QB_Tax_Amount'].fillna(0)
        merged['Has_Tax_Difference'] = abs(merged['Tax_Difference']) > 0.01
    
    # Transaction count differences
    merged['FH_Total_Transactions'] = merged['FH_Payment_Transactions'].fillna(0) + merged['FH_Refund_Transactions'].fillna(0)
    if 'QB_Transaction_Count' in merged.columns:
        merged['Transaction_Count_Difference'] = merged['FH_Total_Transactions'] - merged['QB_Transaction_Count'].fillna(0)
        merged['Has_Transaction_Count_Difference'] = abs(merged['Transaction_Count_Difference']) > 0
    
    # Filter to only rows with differences or missing transactions
    difference_columns = [col for col in merged.columns if col.startswith('Has_') and col.endswith('_Difference')]
    
    if difference_columns:
        # Combine all difference conditions with OR
        has_any_difference = merged[difference_columns[0]]
        for col in difference_columns[1:]:
            has_any_difference = has_any_difference | merged[col]
        
        # Also include rows with missing transactions
        if 'Missing_Transaction_Type' in merged.columns:
            has_missing_transactions = merged['Missing_Transaction_Type'] != 'None'
            has_any_difference = has_any_difference | has_missing_transactions
        
        result = merged[has_any_difference].copy()
    else:
        st.warning("No comparable payment/refund columns found between FareHarbour and QuickBooks.")
        result = pd.DataFrame()
    
    return result

def void_invoices_in_quickbooks(cancelled_data, webhook_url=None):
    """
    Void invoices in QuickBooks using webhook for each document number
    
    Args:
        cancelled_data: DataFrame with cancelled bookings that have open QB invoices
        webhook_url: The n8n webhook URL to call for voiding invoices (uses env var if None)
    
    Returns:
        dict: Results of the voiding process
    """
    # Security check - only allow if feature is enabled
    if not ENABLE_VOID_FEATURE:
        st.error("🚫 Void feature is disabled for security. Contact administrator to enable.")
        return {"success": 0, "failed": 0, "results": [], "error": "Feature disabled"}
    
    if cancelled_data.empty:
        return {"success": 0, "failed": 0, "results": []}
    
    # Use environment variable for webhook URL if not provided
    if webhook_url is None:
        webhook_url = WEBHOOK_URL
        
    # Validate webhook URL
    if not webhook_url or not webhook_url.startswith('https://'):
        st.error("🚫 Invalid or missing webhook URL configuration.")
        return {"success": 0, "failed": 0, "results": [], "error": "Invalid webhook URL"}
    
    results = {
        "success": 0,
        "failed": 0,
        "results": []
    }
    
    # Extract document numbers from the data
    doc_numbers = []
    
    # Try to find document numbers in various columns
    if '#' in cancelled_data.columns:
        potential_docs = cancelled_data['#'].dropna().unique().tolist()
        if potential_docs:
            doc_numbers = potential_docs
    elif 'Doc Number' in cancelled_data.columns:
        potential_docs = cancelled_data['Doc Number'].dropna().unique().tolist()
        if potential_docs:
            doc_numbers = potential_docs
    elif 'Document Number' in cancelled_data.columns:
        potential_docs = cancelled_data['Document Number'].dropna().unique().tolist()
        if potential_docs:
            doc_numbers = potential_docs
    else:
        # Fallback: look for any column that might contain document numbers
        for col in cancelled_data.columns:
            if 'doc' in col.lower() or '#' in col or 'number' in col.lower():
                potential_docs = cancelled_data[col].dropna().unique().tolist()
                if potential_docs:
                    doc_numbers = potential_docs
                    break
    
    if not doc_numbers:
        st.error("No document numbers found to void. Please ensure your QuickBooks data contains document number information.")
        return results
    
    # Create progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, doc_number in enumerate(doc_numbers):
        try:
            # Update progress
            progress = (i + 1) / len(doc_numbers)
            progress_bar.progress(progress)
            status_text.text(f"Voiding invoice {i+1}/{len(doc_numbers)}: {doc_number}")
            
            # Prepare webhook payload
            payload = {
                "doc_number": str(doc_number).strip(),
                "action": "void",
                "source": "fareharbour_reconciliation"
            }
            
            # Add API key if available
            headers = {'Content-Type': 'application/json'}
            if API_KEY:
                headers['Authorization'] = f'Bearer {API_KEY}'
                payload['api_key'] = API_KEY
            
            # Make the webhook call
            start_time = datetime.now()
            
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=30,
                headers=headers
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if response.status_code == 200:
                results["success"] += 1
                results["results"].append({
                    "doc_number": doc_number,
                    "status": "success",
                    "message": f"Successfully voided invoice {doc_number}",
                    "response_time": duration,
                    "response_data": response.text
                })
            else:
                results["failed"] += 1
                results["results"].append({
                    "doc_number": doc_number,
                    "status": "failed",
                    "message": f"Failed to void invoice {doc_number}: HTTP {response.status_code}",
                    "response_time": duration,
                    "response_data": response.text
                })
            
            # 10 second delay between requests
            if i < len(doc_numbers) - 1:  # Don't delay after the last request
                time.sleep(10)
            
        except requests.exceptions.RequestException as e:
            results["failed"] += 1
            results["results"].append({
                "doc_number": doc_number,
                "status": "failed",
                "message": f"Network error voiding invoice {doc_number}: {str(e)}",
                "error_type": type(e).__name__
            })
                
        except Exception as e:
            results["failed"] += 1
            results["results"].append({
                "doc_number": doc_number,
                "status": "failed",
                "message": f"Unexpected error voiding invoice {doc_number}: {str(e)}",
                "error_type": type(e).__name__
            })
    
    # Complete progress
    progress_bar.progress(1.0)
    status_text.text(f"Completed! {results['success']} successful, {results['failed']} failed")
    
    return results

def export_to_excel(dataframes_dict):
    """Export multiple dataframes to Excel with different sheets"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in dataframes_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    processed_data = output.getvalue()
    return processed_data

def load_notes_from_csv(notes_file="reconciliation_notes.csv"):
    """Load existing notes from CSV file"""
    try:
        if os.path.exists(notes_file):
            notes_df = pd.read_csv(notes_file)
            # Ensure we have the required columns
            if 'Booking_ID' in notes_df.columns and 'Notes' in notes_df.columns:
                # Convert Booking_ID to string for consistent comparison
                notes_df['Booking_ID'] = notes_df['Booking_ID'].astype(str)
                return notes_df.set_index('Booking_ID')['Notes'].to_dict()
            else:
                st.warning(f"Notes file {notes_file} exists but doesn't have required columns. Creating new notes structure.")
                return {}
        else:
            return {}
    except Exception as e:
        st.error(f"Error loading notes from {notes_file}: {str(e)}")
        return {}

def save_notes_to_csv(notes_dict, notes_file="reconciliation_notes.csv"):
    """Save notes dictionary to CSV file"""
    try:
        # Convert dictionary to DataFrame
        notes_df = pd.DataFrame([
            {'Booking_ID': booking_id, 'Notes': note, 'Last_Updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            for booking_id, note in notes_dict.items()
            if note.strip()  # Only save non-empty notes
        ])
        
        if not notes_df.empty:
            notes_df.to_csv(notes_file, index=False)
            return True
        else:
            # If no notes to save, create empty file or delete existing one
            if os.path.exists(notes_file):
                os.remove(notes_file)
            return True
    except Exception as e:
        st.error(f"Error saving notes to {notes_file}: {str(e)}")
        return False

def merge_notes_with_data(df, notes_dict, booking_id_col='Booking_ID'):
    """Merge notes with the dataframe"""
    if df.empty:
        return df
    
    # Handle different column names for booking ID
    df_copy = df.copy()
    
    # Map common booking ID column names
    if booking_id_col not in df_copy.columns:
        if 'Booking ID Clean' in df_copy.columns:
            df_copy['Booking_ID'] = df_copy['Booking ID Clean'].astype(str)
        elif 'Booking ID' in df_copy.columns:
            df_copy['Booking_ID'] = df_copy['Booking ID'].astype(str)
        elif 'FH_Booking_ID' in df_copy.columns:
            df_copy['Booking_ID'] = df_copy['FH_Booking_ID'].astype(str)
        else:
            st.warning(f"Could not find booking ID column. Available columns: {list(df_copy.columns)}")
            df_copy['Booking_ID'] = range(len(df_copy))  # Use row index as fallback
    else:
        df_copy['Booking_ID'] = df_copy[booking_id_col].astype(str)
    
    # Add notes column
    df_copy['Notes'] = df_copy['Booking_ID'].map(notes_dict).fillna('')
    
    return df_copy

def create_notes_editor(df, table_type, key_suffix):
    """Create a reusable notes editor component"""
    if df.empty:
        return df, {}
    
    # Prepare display columns with Notes first
    display_cols = ['Booking_ID', 'Notes']
    
    # Add other important columns based on what's available
    important_cols = ['Created At Date', 'Contact', 'Item', 'Start Date', 'Total', 'Total Paid', 
                     'Open_Balance', 'Amount', 'Cancelled?', 'Is_Cancelled', 'Is_Paid']
    
    for col in important_cols:
        if col in df.columns and col not in display_cols:
            display_cols.append(col)
    
    # Add remaining columns
    remaining_cols = [col for col in df.columns if col not in display_cols]
    display_cols.extend(remaining_cols)
    
    # Filter to only include columns that exist
    display_cols = [col for col in display_cols if col in df.columns]
    
    # Use data editor for interactive editing
    st.info("💡 You can edit notes directly in the table below. Click 'Save Notes' to persist your changes.")
    
    edited_df = st.data_editor(
        df[display_cols],
        column_config={
            "Notes": st.column_config.TextColumn(
                "Notes",
                help=f"Add your notes for this {table_type.lower()} issue",
                max_chars=500,
                width="medium"
            ),
            "Booking_ID": st.column_config.TextColumn(
                "Booking ID",
                help="FareHarbour Booking ID",
                disabled=True,
                width="small"
            )
        },
        hide_index=True,
        use_container_width=True,
        key=f"{table_type.lower().replace(' ', '_')}_editor_{key_suffix}"
    )
    
    return edited_df, display_cols

def save_table_notes(edited_df, notes_file, table_type):
    """Save notes for a specific table type"""
    # Extract notes from edited dataframe
    notes_to_save = {}
    for _, row in edited_df.iterrows():
        booking_id = str(row['Booking_ID'])
        note = row['Notes'] if pd.notna(row['Notes']) else ''
        if note.strip():  # Only save non-empty notes
            notes_to_save[booking_id] = note.strip()
    
    # Save to CSV
    if save_notes_to_csv(notes_to_save, notes_file):
        st.success(f"✅ Successfully saved notes for {len(notes_to_save)} {table_type.lower()} records!")
        st.balloons()
        return True
    else:
        st.error("❌ Failed to save notes. Please try again.")
        return False

def show_notes_file_info(notes_file, table_type, existing_notes):
    """Show information about the notes file"""
    if os.path.exists(notes_file):
        file_stat = os.stat(notes_file)
        file_size = file_stat.st_size
        file_modified = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        with st.expander(f"📁 {table_type} Notes File Information"):
            st.write(f"**File:** {notes_file}")
            st.write(f"**Size:** {file_size} bytes")
            st.write(f"**Last Modified:** {file_modified}")
            st.write(f"**Total Saved Notes:** {len(existing_notes)}")
            
            if st.button(f"🗑️ Clear All {table_type} Notes", key=f"clear_{table_type.lower().replace(' ', '_')}_notes"):
                if os.path.exists(notes_file):
                    os.remove(notes_file)
                    st.success(f"All {table_type.lower()} notes cleared!")
                    st.rerun()

def manage_tours_and_fees():
    """Tours and Fees Management Page"""
    st.title("🎯 Tours & Fees Management")

    # Compact CSS styling
    st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {gap: 4px; margin-bottom: 1rem;}
    .stTabs [data-baseweb="tab"] {padding: 8px 16px; font-size: 0.9rem;}
    .stButton > button {border-radius: 6px; margin: 2px;}
    .element-container {margin-bottom: 0.5rem;}
    </style>
    """, unsafe_allow_html=True)

    # Create tabs for different operations
    tab1, tab2, tab3 = st.tabs(["🎪 Tours", "💰 Fees", "🔗 Mappings"])
    
    with tab1:
        st.subheader("🎪 Tours Management")

        # Add new tour
        col1, col2 = st.columns([3, 1])
        with col1:
            new_tour_name = st.text_input("New Tour Name", key="new_tour", placeholder="Enter tour name")
        with col2:
            if st.button("➕ Add Tour", key="add_tour_btn", type="primary"):
                if new_tour_name.strip():
                    result = execute_query("INSERT INTO tours (name) VALUES (:name)", {"name": new_tour_name.strip()})
                    if result:
                        st.success(f"✅ Tour '{new_tour_name}' added!")
                        st.rerun()
                else:
                    st.error("❌ Please enter a tour name")
        
        # Edit existing tours
        tours = execute_query("SELECT id, name FROM tours ORDER BY name")

        if tours:
            st.write(f"**{len(tours)} tours available**")

            # Initialize session state for tour editing
            if 'tour_edits' not in st.session_state:
                st.session_state.tour_edits = {tour[0]: {'name': tour[1]} for tour in tours}

            for tour in tours:
                tour_id, original_name = tour[0], tour[1]
                col1, col2 = st.columns([4, 1])
                with col1:
                    new_name = st.text_input(
                        f"Tour {tour_id}",
                        value=st.session_state.tour_edits.get(tour_id, {}).get('name', original_name),
                        key=f"tour_name_{tour_id}",
                        label_visibility="collapsed"
                    )
                    st.session_state.tour_edits[tour_id] = {'name': new_name}

                with col2:
                    if st.button("🗑️", key=f"delete_tour_{tour_id}", help=f"Delete '{original_name}'"):
                        result = execute_query("DELETE FROM tours WHERE id = :id", {"id": tour_id})
                        if result:
                            st.success(f"✅ Tour '{original_name}' deleted!")
                            if tour_id in st.session_state.tour_edits:
                                del st.session_state.tour_edits[tour_id]
                            st.rerun()

            # Quick actions
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔄 Reset All", key="reset_tours"):
                    for tour in tours:
                        tour_id = tour[0]
                        st.session_state.tour_edits[tour_id] = {'name': tour[1]}
                    st.success("✅ Reset all tours!")
                    st.rerun()

            with col2:
                if st.button("💾 Save All", key="save_all_tours", type="primary"):
                    updated_count = 0
                    for tour_id, edit_data in st.session_state.tour_edits.items():
                        if edit_data['name'].strip():
                            result = execute_query(
                                "UPDATE tours SET name = :name, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                                {"name": edit_data['name'].strip(), "id": tour_id}
                            )
                            if result:
                                updated_count += 1
                    if updated_count > 0:
                        st.success(f"✅ Updated {updated_count} tour(s)!")
                        st.rerun()

            with col3:
                if st.button("🗑️ Delete All", key="delete_all_tours"):
                    if st.session_state.get('confirm_delete_all_tours', False):
                        result = execute_query("DELETE FROM tours")
                        if result:
                            st.success("✅ All tours deleted!")
                            st.session_state.tour_edits = {}
                            st.session_state.confirm_delete_all_tours = False
                            st.rerun()
                    else:
                        st.session_state.confirm_delete_all_tours = True
                        st.warning("⚠️ Click again to confirm deletion of ALL tours!")
            
        else:
            st.info("🎪 No tours yet. Add your first tour above to get started!")
    
    with tab2:
        st.subheader("💰 Fees Management")

        # Add new fee
        col1, col2, col3 = st.columns([3, 1.5, 1])
        with col1:
            new_fee_name = st.text_input("Fee Name", key="new_fee", placeholder="Enter fee name")
        with col2:
            new_fee_amount = st.number_input("Amount", min_value=0.0, step=0.01, key="new_fee_amount")
        with col3:
            if st.button("➕ Add", key="add_fee_btn", type="primary"):
                if new_fee_name.strip():
                    result = execute_query(
                        "INSERT INTO fees (name, per_person_amount, apply_to_all) VALUES (:name, :amount, :apply_all)",
                        {"name": new_fee_name.strip(), "amount": new_fee_amount, "apply_all": False}
                    )
                    if result:
                        st.success(f"✅ Fee '{new_fee_name}' added!")
                        st.rerun()
                else:
                    st.error("❌ Please enter a fee name")
        
        # Edit existing fees
        fees = execute_query("SELECT id, name, per_person_amount FROM fees ORDER BY name")

        if fees:
            st.write(f"**{len(fees)} fees available**")

            # Initialize session state for fee editing
            if 'fee_edits' not in st.session_state:
                st.session_state.fee_edits = {fee[0]: {'name': fee[1], 'amount': float(fee[2])} for fee in fees}

            for fee in fees:
                fee_id, original_name, original_amount = fee[0], fee[1], fee[2]
                col1, col2, col3 = st.columns([3, 1.5, 1])

                with col1:
                    new_name = st.text_input(
                        f"Fee {fee_id}",
                        value=st.session_state.fee_edits.get(fee_id, {}).get('name', original_name),
                        key=f"fee_name_{fee_id}",
                        label_visibility="collapsed"
                    )
                    st.session_state.fee_edits[fee_id] = st.session_state.fee_edits.get(fee_id, {})
                    st.session_state.fee_edits[fee_id]['name'] = new_name

                with col2:
                    new_amount = st.number_input(
                        f"Amount {fee_id}",
                        value=st.session_state.fee_edits.get(fee_id, {}).get('amount', float(original_amount)),
                        min_value=0.0,
                        step=0.01,
                        key=f"fee_amount_{fee_id}",
                        label_visibility="collapsed"
                    )
                    st.session_state.fee_edits[fee_id]['amount'] = new_amount

                with col3:
                    if st.button("🗑️", key=f"delete_fee_{fee_id}", help=f"Delete '{original_name}'"):
                        result = execute_query("DELETE FROM fees WHERE id = :id", {"id": fee_id})
                        if result:
                            st.success(f"✅ Fee '{original_name}' deleted!")
                            if fee_id in st.session_state.fee_edits:
                                del st.session_state.fee_edits[fee_id]
                            st.rerun()

            # Quick actions
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔄 Reset All", key="reset_fees"):
                    for fee in fees:
                        fee_id = fee[0]
                        st.session_state.fee_edits[fee_id] = {'name': fee[1], 'amount': float(fee[2])}
                    st.success("✅ Reset all fees!")
                    st.rerun()

            with col2:
                if st.button("💾 Save All", key="save_all_fees", type="primary"):
                    updated_count = 0
                    for fee_id, edit_data in st.session_state.fee_edits.items():
                        if edit_data['name'].strip():
                            result = execute_query(
                                "UPDATE fees SET name = :name, per_person_amount = :amount, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                                {"name": edit_data['name'].strip(), "amount": edit_data['amount'], "id": fee_id}
                            )
                            if result:
                                updated_count += 1
                    if updated_count > 0:
                        st.success(f"✅ Updated {updated_count} fee(s)!")
                        st.rerun()

            with col3:
                if st.button("🗑️ Delete All", key="delete_all_fees"):
                    if st.session_state.get('confirm_delete_all', False):
                        result = execute_query("DELETE FROM fees")
                        if result:
                            st.success("✅ All fees deleted!")
                            st.session_state.fee_edits = {}
                            st.session_state.confirm_delete_all = False
                            st.rerun()
                    else:
                        st.session_state.confirm_delete_all = True
                        st.warning("⚠️ Click again to confirm deletion of ALL fees!")

        else:
            st.info("💰 No fees yet. Add your first fee above to get started!")
    
    with tab3:
        st.subheader("🔗 Tour-Fee Mappings")

        # Get tours and fees
        tours = execute_query("SELECT id, name FROM tours ORDER BY name")
        fees = execute_query("SELECT id, name, per_person_amount FROM fees ORDER BY name")

        if not tours:
            st.warning("🎪 Add tours first in the Tours tab.")
            return

        if not fees:
            st.warning("💰 Add fees first in the Fees tab.")
            return
        
        # Get existing mappings
        existing_mappings = execute_query("SELECT tour_id, fee_id FROM tour_fees")
        existing_set = set((mapping[0], mapping[1]) for mapping in existing_mappings) if existing_mappings else set()

        # Create matrix data
        matrix_data = []
        for tour in tours:
            tour_id, tour_name = tour[0], tour[1]
            row = {"Tour": tour_name, "tour_id": tour_id}
            for fee in fees:
                fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
                row[f"{fee_name} (${fee_amount})"] = (tour_id, fee_id) in existing_set
            matrix_data.append(row)

        df = pd.DataFrame(matrix_data)
        st.write(f"**{len(tours)} tours × {len(fees)} fees** - Check boxes to assign fees to tours")
        
        # Configure data editor
        column_config = {
            "Tour": st.column_config.TextColumn("Tour Name", disabled=True, width="medium"),
            "tour_id": None
        }

        for fee in fees:
            fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
            column_config[f"{fee_name} (${fee_amount})"] = st.column_config.CheckboxColumn(
                fee_name, default=False, width="small"
            )

        edited_df = st.data_editor(
            df,
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
            key="tour_fee_mappings_editor"
        )
        
        # Save button
        if not edited_df.equals(df):
            st.warning("⚠️ You have unsaved changes!")

        col1, col2, col3 = st.columns(3)
        with col2:
            if st.button("💾 Save Changes", key="save_mappings_table", type="primary"):
                try:
                    old_mappings = set()
                    for _, row in df.iterrows():
                        tour_id = row["tour_id"]
                        for fee in fees:
                            fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
                            if row[f"{fee_name} (${fee_amount})"]:
                                old_mappings.add((tour_id, fee_id))

                    new_mappings = set()
                    for _, row in edited_df.iterrows():
                        tour_id = row["tour_id"]
                        for fee in fees:
                            fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
                            if row[f"{fee_name} (${fee_amount})"]:
                                new_mappings.add((tour_id, fee_id))

                    added = new_mappings - old_mappings
                    removed = old_mappings - new_mappings

                    if added or removed:
                        execute_query("DELETE FROM tour_fees")
                        if new_mappings:
                            for tour_id, fee_id in new_mappings:
                                execute_query("INSERT INTO tour_fees (tour_id, fee_id) VALUES (:tour_id, :fee_id)",
                                            {"tour_id": tour_id, "fee_id": fee_id})

                        st.success(f"✅ Saved! {len(added)} added, {len(removed)} removed. Total: {len(new_mappings)}")
                        st.rerun()
                    else:
                        st.info("💡 No changes detected")

                except Exception as e:
                    st.error(f"❌ Error saving: {e}")

        # Current mappings summary
        st.markdown("---")
        current_mappings = execute_query("""
            SELECT t.name as tour_name, f.name as fee_name, f.per_person_amount
            FROM tour_fees tf
            JOIN tours t ON tf.tour_id = t.id
            JOIN fees f ON tf.fee_id = f.id
            ORDER BY t.name, f.name
        """)

        if current_mappings:
            st.subheader("📊 Current Mappings")
            tour_mappings = {}
            for mapping in current_mappings:
                tour_name, fee_name, amount = mapping
                if tour_name not in tour_mappings:
                    tour_mappings[tour_name] = []
                tour_mappings[tour_name].append(f"{fee_name} (${amount})")

            for tour_name, fee_list in tour_mappings.items():
                with st.expander(f"🎪 {tour_name} ({len(fee_list)} fees)"):
                    for fee_info in fee_list:
                        st.write(f"• {fee_info}")
        else:
            st.info("💡 No mappings saved yet. Use the table above to assign fees to tours.")

def sales_report_analysis():
    """Sales Report Analysis Page with CSV Upload and Pivot Tables"""
    st.title("📊 Sales Report Analysis")

    # Compact CSS
    st.markdown("""
    <style>
    .stDataFrame {border: 1px solid #e9ecef; border-radius: 6px;}
    </style>
    """, unsafe_allow_html=True)
    
    # File upload section
    st.sidebar.header("📁 Sales Report Upload")
    
    sales_csv_file = st.sidebar.file_uploader(
        "Upload Sales Report CSV",
        type=['csv'],
        help="Upload the FareHarbour sales report CSV file"
    )
    
    if sales_csv_file is not None:
        try:
            # Load CSV with proper header handling (skip first row, use second row as headers)
            with st.spinner("Loading and processing sales report..."):
                # Read CSV and handle headers properly
                df = load_sales_csv_data(sales_csv_file)
                
            if df is not None and not df.empty:
                # Display data overview
                st.markdown('<div class="metrics-container">', unsafe_allow_html=True)
                st.subheader("📈 Data Overview")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Records", len(df))
                with col2:
                    unique_tours = df['Item'].nunique() if 'Item' in df.columns else 0
                    st.metric("Unique Tours", unique_tours)
                with col3:
                    total_pax = df['# of Pax'].sum() if '# of Pax' in df.columns else 0
                    st.metric("Total Guests", f"{total_pax:,}")
                with col4:
                    total_revenue = df['Total Paid'].sum() if 'Total Paid' in df.columns else 0
                    st.metric("Total Revenue", f"${total_revenue:,.2f}")
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Create tabs for different analyses
                tab1, tab2 = st.tabs(["📊 Pivot Analysis", "📈 Payment & Affiliate Breakdown"])
                
                with tab1:
                    # Create pivot table and filters
                    create_sales_pivot_analysis(df)
                
                with tab2:
                    # Create detailed breakdown analysis
                    create_payment_affiliate_breakdown(df)
                
            else:
                st.error("❌ Failed to load CSV data. Please check the file format.")
                
        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
            st.info("💡 Make sure the CSV has the correct format with headers starting on the second row.")
    
    else:
        # Instructions for file format
        st.info("👆 Upload a FareHarbour Sales Report CSV file to begin analysis")
        
        st.markdown("""
        ### 📋 Expected CSV Format
        
        The CSV file should have:
        - **Row 1**: May contain metadata (will be skipped)
        - **Row 2**: Column headers including Item, # of Pax, payments, refunds, etc.
        - **Row 3+**: Actual data records
        
        **Key columns for analysis:**
        - `Item`: Tour/activity name
        - `# of Pax`: Number of guests
        - `Total Paid`: Total amount paid
        - `Refund Gross`: Refund amounts
        - `Payment Gross`: Payment amounts
        - `Receivable from Affiliate`: Affiliate amounts
        """)

def load_sales_csv_data(file):
    """Load sales CSV data with proper header handling"""
    try:
        # Read the CSV file, skipping the first row and using second row as headers
        df = pd.read_csv(file, skiprows=1)
        
        # Clean column names (remove extra spaces, etc.)
        df.columns = df.columns.str.strip()
        
        # Convert numeric columns - handle currency format properly
        numeric_columns = ['# of Pax', 'Total Paid', 'Payment Gross', 'Refund Gross', 
                          'Net Revenue Collected', 'Receivable from Affiliate', 
                          'Received from Affiliate', 'Total', 'Subtotal', 'Gross',
                          'Processing Fee', 'Net', 'Payment Processing Fee', 'Payment Net',
                          'Refund Processing Fee', 'Refund Net', 'Subtotal Paid',
                          'Dashboard Tax Rate (5%) Paid', 'Tax Paid']
        
        for col in numeric_columns:
            if col in df.columns:
                # Handle currency format: remove $, commas, and handle negative values
                # Convert to string first, then clean
                df[col] = df[col].astype(str)
                # Remove currency symbols, commas, and handle negative values in parentheses
                df[col] = df[col].str.replace('[$,"]', '', regex=True)
                # Handle negative values in format like "-$0.81"
                df[col] = df[col].str.replace('-', '', regex=False)
                # Convert to numeric
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Filter out rows where Item is empty or NaN (likely empty rows)
        if 'Item' in df.columns:
            df = df.dropna(subset=['Item'])
            df = df[df['Item'].str.strip() != '']
            # Also filter out rows where Item is just quotes or empty string
            df = df[~df['Item'].isin(['""', '', 'nan'])]
        
        # Debug: Show first few rows and column info
        st.info(f"📊 Loaded {len(df)} records with {len(df.columns)} columns")
        if len(df) > 0:
            st.info(f"🎪 Found {df['Item'].nunique()} unique tours")
            # Show sample of data
            with st.expander("🔍 Preview First 3 Records"):
                st.dataframe(df.head(3))
        
        return df
        
    except Exception as e:
        st.error(f"Error loading CSV: {str(e)}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None

def create_sales_pivot_analysis(df):
    """Create pivot table analysis with filtering"""
    st.markdown('<div class="filter-container">', unsafe_allow_html=True)
    st.subheader("🔍 Filters & Analysis")
    
    # Filtering options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Tour filter
        tours_available = ['All'] + sorted(df['Item'].unique().tolist()) if 'Item' in df.columns else ['All']
        selected_tours = st.multiselect(
            "Select Tours", 
            options=tours_available,
            default=['All'],
            help="Filter by specific tours or leave 'All' selected"
        )
    
    with col2:
        # Date range filter (if date columns exist)
        if 'Created At Date' in df.columns:
            df['Created At Date'] = pd.to_datetime(df['Created At Date'], errors='coerce')
            min_date = df['Created At Date'].min()
            max_date = df['Created At Date'].max()
            if not pd.isna(min_date) and not pd.isna(max_date):
                date_range = st.date_input(
                    "Date Range",
                    value=(min_date, max_date),
                    min_value=min_date,
                    max_value=max_date
                )
            else:
                date_range = None
        else:
            date_range = None
    
    with col3:
        # Minimum amount filter
        min_amount = st.number_input(
            "Minimum Total Amount",
            min_value=0.0,
            value=0.0,
            step=10.0,
            help="Filter records with total amount >= this value"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Apply filters
    filtered_df = df.copy()
    
    # Tour filter
    if 'All' not in selected_tours and selected_tours:
        filtered_df = filtered_df[filtered_df['Item'].isin(selected_tours)]
    
    # Date filter
    if date_range and len(date_range) == 2 and 'Created At Date' in df.columns:
        start_date, end_date = date_range
        filtered_df = filtered_df[
            (filtered_df['Created At Date'] >= pd.Timestamp(start_date)) &
            (filtered_df['Created At Date'] <= pd.Timestamp(end_date))
        ]
    
    # Amount filter
    if 'Total Paid' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Total Paid'] >= min_amount]
    
    # Create pivot table
    if not filtered_df.empty:
        pivot_data = create_tour_pivot_table(filtered_df)
        
        # Display pivot table
        st.subheader("📊 Tour Summary Pivot Table")
        
        if not pivot_data.empty:
            # Format the pivot table for display
            display_pivot_table(pivot_data)
            
            # Export functionality
            st.subheader("📥 Export Data")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📊 Export Pivot Table", help="Download pivot table as CSV"):
                    csv = pivot_data.to_csv(index=False)
                    st.download_button(
                        label="💾 Download CSV",
                        data=csv,
                        file_name=f"sales_pivot_table_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime='text/csv'
                    )
            
            with col2:
                if st.button("📋 Export Filtered Data", help="Download filtered raw data as CSV"):
                    csv = filtered_df.to_csv(index=False)
                    st.download_button(
                        label="💾 Download Raw Data CSV",
                        data=csv,
                        file_name=f"sales_filtered_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime='text/csv'
                    )
            
            with col3:
                if st.button("📚 Export QB Journal", help="Generate QuickBooks journal entries"):
                    journal_df = create_quickbooks_journal(pivot_data, filtered_df)
                    if not journal_df.empty:
                        csv = journal_df.to_csv(index=False)
                        st.download_button(
                            label="💾 Download Journal CSV",
                            data=csv,
                            file_name=f"quickbooks_journal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime='text/csv'
                        )
                        
                        # Show preview of journal entries
                        with st.expander("🔍 Preview Journal Entries"):
                            st.dataframe(journal_df, use_container_width=True)
        else:
            st.warning("⚠️ No data available for pivot table creation.")
    else:
        st.warning("⚠️ No data matches the selected filters.")

def create_tour_pivot_table(df):
    """Create pivot table summarizing data by tour with fee splits from database"""
    try:
        # Define the columns we want to aggregate
        pivot_columns = {
            'Item': 'Tour Name',
            '# of Pax': 'Total Guests',
            'Total Paid': 'Total Revenue',
            'Payment Gross': 'Gross Payments', 
            'Refund Gross': 'Total Refunds',
            'Net Revenue Collected': 'Net Revenue',
            'Receivable from Affiliate': 'Receivable from Affiliate',
            'Received from Affiliate': 'Received from Affiliate',
            'Subtotal': 'Subtotal (Ex-Tax)'
        }
        
        # Check which columns exist in the dataframe
        available_columns = {k: v for k, v in pivot_columns.items() if k in df.columns}
        
        if 'Item' not in available_columns:
            st.error("❌ 'Item' column not found in CSV. Cannot create pivot table.")
            return pd.DataFrame()
        
        # Group by Item and aggregate
        agg_dict = {}
        for col, label in available_columns.items():
            if col == 'Item':
                continue  # Skip the groupby column
            elif col == '# of Pax':
                agg_dict[col] = 'sum'  # Sum total guests
            else:
                agg_dict[col] = 'sum'  # Sum financial amounts
        
        if not agg_dict:
            st.error("❌ No numeric columns found for aggregation.")
            return pd.DataFrame()
        
        # Create the pivot table
        pivot_df = df.groupby('Item').agg(agg_dict).reset_index()
        
        # Rename columns for better display
        column_mapping = {col: available_columns[col] for col in pivot_df.columns if col in available_columns}
        pivot_df.rename(columns=column_mapping, inplace=True)
        
        # Add booking count
        booking_counts = df.groupby('Item').size().reset_index(name='Booking Count')
        pivot_df = pivot_df.merge(booking_counts, left_on='Tour Name', right_on='Item', how='left').drop('Item', axis=1)
        
        # Integrate with database to calculate fee splits
        pivot_df = calculate_fee_splits(pivot_df)
        
        # Add calculated fields
        if 'Total Revenue' in pivot_df.columns and 'Total Refunds' in pivot_df.columns:
            pivot_df['Net After Refunds'] = pivot_df['Total Revenue'] - pivot_df['Total Refunds']
        
        # Calculate averages
        if 'Total Revenue' in pivot_df.columns and 'Total Guests' in pivot_df.columns:
            pivot_df['Revenue per Guest'] = pivot_df['Total Revenue'] / pivot_df['Total Guests'].replace(0, 1)
        
        # Sort by total revenue descending
        if 'Total Revenue' in pivot_df.columns:
            pivot_df = pivot_df.sort_values('Total Revenue', ascending=False)
        
        return pivot_df
        
    except Exception as e:
        st.error(f"❌ Error creating pivot table: {str(e)}")
        return pd.DataFrame()

def calculate_fee_splits(pivot_df):
    """Calculate tour revenue vs fee revenue splits using database mappings"""
    try:
        # Get tour-fee mappings from database
        mappings = execute_query("""
            SELECT t.name as tour_name, f.name as fee_name, f.per_person_amount
            FROM tour_fees tf
            JOIN tours t ON tf.tour_id = t.id
            JOIN fees f ON tf.fee_id = f.id
            ORDER BY t.name, f.name
        """)
        
        if not mappings:
            st.info("💡 No tour-fee mappings found in database. Showing raw revenue data.")
            return pivot_df
        
        # Convert mappings to DataFrame for easier processing
        mappings_df = pd.DataFrame(mappings, columns=['tour_name', 'fee_name', 'per_person_amount'])
        mappings_df['per_person_amount'] = pd.to_numeric(mappings_df['per_person_amount'], errors='coerce').fillna(0)
        
        # Add fee calculation columns to pivot table
        pivot_df['Total Fees per Person'] = 0.0
        pivot_df['Total Fee Revenue'] = 0.0
        pivot_df['Tour Revenue (Net of Fees)'] = 0.0
        pivot_df['Fee Details'] = ""
        
        # Process each tour
        for idx, row in pivot_df.iterrows():
            tour_name = row['Tour Name']
            total_guests = row.get('Total Guests', 0)
            subtotal = row.get('Subtotal (Ex-Tax)', row.get('Total Revenue', 0))
            
            # Find fees for this tour
            tour_fees = mappings_df[mappings_df['tour_name'] == tour_name]
            
            if not tour_fees.empty:
                # Calculate total fees per person
                total_fees_per_person = tour_fees['per_person_amount'].sum()
                total_fee_revenue = total_fees_per_person * total_guests
                tour_revenue_net = subtotal - total_fee_revenue
                
                # Create fee details string
                fee_details = []
                for _, fee_row in tour_fees.iterrows():
                    fee_amount = fee_row['per_person_amount'] * total_guests
                    if fee_amount > 0:
                        fee_details.append(f"{fee_row['fee_name']}: ${fee_amount:.2f}")
                
                # Update pivot table
                pivot_df.loc[idx, 'Total Fees per Person'] = total_fees_per_person
                pivot_df.loc[idx, 'Total Fee Revenue'] = total_fee_revenue
                pivot_df.loc[idx, 'Tour Revenue (Net of Fees)'] = max(0, tour_revenue_net)
                pivot_df.loc[idx, 'Fee Details'] = "; ".join(fee_details) if fee_details else "No fees"
            else:
                # No fees mapped for this tour
                pivot_df.loc[idx, 'Tour Revenue (Net of Fees)'] = subtotal
                pivot_df.loc[idx, 'Fee Details'] = "No fees mapped"
        
        return pivot_df
        
    except Exception as e:
        st.error(f"❌ Error calculating fee splits: {str(e)}")
        return pivot_df

def create_quickbooks_journal(pivot_df, raw_df):
    """Create QuickBooks journal entries from pivot table data with payment type splits"""
    try:
        journal_entries = []
        entry_date = datetime.now().strftime('%Y-%m-%d')
        
        # Get fee mappings for detailed breakdown
        mappings = execute_query("""
            SELECT t.name as tour_name, f.name as fee_name, f.per_person_amount
            FROM tour_fees tf
            JOIN tours t ON tf.tour_id = t.id
            JOIN fees f ON tf.fee_id = f.id
            ORDER BY t.name, f.name
        """)
        
        mappings_df = pd.DataFrame(mappings, columns=['tour_name', 'fee_name', 'per_person_amount']) if mappings else pd.DataFrame()
        if not mappings_df.empty:
            mappings_df['per_person_amount'] = pd.to_numeric(mappings_df['per_person_amount'], errors='coerce').fillna(0)
        
        entry_number = 1
        
        # Process each tour in the pivot table
        for _, row in pivot_df.iterrows():
            tour_name = row['Tour Name']
            total_guests = pd.to_numeric(row.get('Total Guests', 0), errors='coerce')
            tour_revenue = pd.to_numeric(row.get('Tour Revenue (Net of Fees)', 0), errors='coerce')
            total_fee_revenue = pd.to_numeric(row.get('Total Fee Revenue', 0), errors='coerce')
            receivable_affiliate = pd.to_numeric(row.get('Receivable from Affiliate', 0), errors='coerce')
            received_affiliate = pd.to_numeric(row.get('Received from Affiliate', 0), errors='coerce')
            
            # Skip if no significant amounts
            if tour_revenue <= 0 and total_fee_revenue <= 0 and receivable_affiliate <= 0 and received_affiliate <= 0:
                continue
            
            # Get payment breakdown for this tour from raw data
            tour_transactions = raw_df[raw_df['Item'] == tour_name].copy()
            
            if not tour_transactions.empty:
                # Calculate payment type splits for this tour
                payment_splits = calculate_payment_type_splits(tour_transactions, tour_revenue, total_fee_revenue)
                
                # 1. TOUR REVENUE ENTRIES (split by payment type)
                if tour_revenue > 0:
                    for payment_type, amount in payment_splits['tour_revenue'].items():
                        if amount > 0:
                            # Credit: Tour Revenue
                            journal_entries.append({
                                'Entry Number': f'JE{entry_number:04d}',
                                'Date': entry_date,
                                'Account': f'Tour Revenue - {tour_name}',
                                'Description': f'Tour revenue for {tour_name} - {payment_type}',
                                'Debit': '',
                                'Credit': f'{amount:.2f}',
                                'Memo': f'Net tour revenue after fees - {payment_type}'
                            })
                            
                            # Debit: Payment Type Account
                            debit_account = get_payment_account(payment_type)
                            journal_entries.append({
                                'Entry Number': f'JE{entry_number:04d}',
                                'Date': entry_date,
                                'Account': debit_account,
                                'Description': f'Tour revenue - {payment_type} for {tour_name}',
                                'Debit': f'{amount:.2f}',
                                'Credit': '',
                                'Memo': f'Tour revenue - {payment_type}'
                            })
                            entry_number += 1
                
                # 2. FEE REVENUE ENTRIES (split by payment type and fee type)
                if not mappings_df.empty and total_fee_revenue > 0:
                    tour_fees = mappings_df[mappings_df['tour_name'] == tour_name]
                    
                    for _, fee_row in tour_fees.iterrows():
                        fee_amount = fee_row['per_person_amount'] * total_guests
                        if fee_amount > 0:
                            fee_name = fee_row['fee_name']
                            
                            # Split fee revenue by payment type
                            for payment_type, proportion in payment_splits['proportions'].items():
                                payment_fee_amount = fee_amount * proportion
                                if payment_fee_amount > 0:
                                    # Credit: Specific Fee Revenue
                                    journal_entries.append({
                                        'Entry Number': f'JE{entry_number:04d}',
                                        'Date': entry_date,
                                        'Account': f'Fee Revenue - {fee_name}',
                                        'Description': f'{fee_name} for {tour_name} - {payment_type}',
                                        'Debit': '',
                                        'Credit': f'{payment_fee_amount:.2f}',
                                        'Memo': f'Fee revenue - {fee_name} - {payment_type}'
                                    })
                                    
                                    # Debit: Payment Type Account
                                    debit_account = get_payment_account(payment_type)
                                    journal_entries.append({
                                        'Entry Number': f'JE{entry_number:04d}',
                                        'Date': entry_date,
                                        'Account': debit_account,
                                        'Description': f'Fee revenue - {payment_type} for {fee_name}',
                                        'Debit': f'{payment_fee_amount:.2f}',
                                        'Credit': '',
                                        'Memo': f'Fee receivable - {fee_name} - {payment_type}'
                                    })
                                    entry_number += 1
            
            # 3. AFFILIATE ENTRIES (separate from payment splits)
            if receivable_affiliate > 0:
                # Debit: Commission Expense, Credit: Accounts Payable to Affiliate
                journal_entries.append({
                    'Entry Number': f'JE{entry_number:04d}',
                    'Date': entry_date,
                    'Account': 'Affiliate Commission Expense',
                    'Description': f'Commission expense for {tour_name}',
                    'Debit': f'{receivable_affiliate:.2f}',
                    'Credit': '',
                    'Memo': f'Affiliate commission - {tour_name}'
                })
                
                journal_entries.append({
                    'Entry Number': f'JE{entry_number:04d}',
                    'Date': entry_date,
                    'Account': f'Accounts Payable - Affiliates',
                    'Description': f'Amount due to affiliate for {tour_name}',
                    'Debit': '',
                    'Credit': f'{receivable_affiliate:.2f}',
                    'Memo': f'Affiliate commission due - {tour_name}'
                })
                entry_number += 1
            
            if received_affiliate > 0:
                # Debit: Cash, Credit: Accounts Payable to Affiliate
                journal_entries.append({
                    'Entry Number': f'JE{entry_number:04d}',
                    'Date': entry_date,
                    'Account': 'Cash - Operating',
                    'Description': f'Payment received from affiliate for {tour_name}',
                    'Debit': f'{received_affiliate:.2f}',
                    'Credit': '',
                    'Memo': f'Affiliate payment received - {tour_name}'
                })
                
                journal_entries.append({
                    'Entry Number': f'JE{entry_number:04d}',
                    'Date': entry_date,
                    'Account': f'Accounts Payable - Affiliates',
                    'Description': f'Payment from affiliate for {tour_name}',
                    'Debit': '',
                    'Credit': f'{received_affiliate:.2f}',
                    'Memo': f'Affiliate payment - {tour_name}'
                })
                entry_number += 1
        
        # Convert to DataFrame
        if journal_entries:
            journal_df = pd.DataFrame(journal_entries)
            return journal_df
        else:
            st.warning("⚠️ No journal entries generated. Check if data contains valid amounts.")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Error creating QuickBooks journal: {str(e)}")
        import traceback
        st.error(f"Details: {traceback.format_exc()}")
        return pd.DataFrame()

def calculate_payment_type_splits(transactions, tour_revenue, total_fee_revenue):
    """Calculate how revenue should be split by payment type based on transaction data"""
    try:
        # Group by payment type and sum amounts
        if 'Payment Type' in transactions.columns:
            payment_summary = transactions.groupby('Payment Type').agg({
                'Total Paid': 'sum',
                '# of Pax': 'sum'
            }).reset_index()
        else:
            # Fallback if Payment Type column doesn't exist
            payment_summary = pd.DataFrame({
                'Payment Type': ['unknown'],
                'Total Paid': [transactions['Total Paid'].sum() if 'Total Paid' in transactions.columns else 0],
                '# of Pax': [transactions['# of Pax'].sum() if '# of Pax' in transactions.columns else 0]
            })
        
        total_payments = payment_summary['Total Paid'].sum()
        
        # Calculate proportions for each payment type
        payment_splits = {
            'tour_revenue': {},
            'fee_revenue': {},
            'proportions': {}
        }
        
        for _, payment_row in payment_summary.iterrows():
            payment_type = payment_row['Payment Type']
            payment_amount = payment_row['Total Paid']
            
            if total_payments > 0:
                proportion = payment_amount / total_payments
            else:
                proportion = 1.0 / len(payment_summary)  # Equal split if no payment data
            
            payment_splits['tour_revenue'][payment_type] = tour_revenue * proportion
            payment_splits['fee_revenue'][payment_type] = total_fee_revenue * proportion
            payment_splits['proportions'][payment_type] = proportion
        
        return payment_splits
        
    except Exception as e:
        # Fallback to single payment type
        return {
            'tour_revenue': {'unknown': tour_revenue},
            'fee_revenue': {'unknown': total_fee_revenue},
            'proportions': {'unknown': 1.0}
        }

def get_payment_account(payment_type):
    """Map payment type to appropriate GL account"""
    payment_type_lower = payment_type.lower().strip()
    
    # Map payment types to GL accounts
    account_mapping = {
        'credit card': 'Credit Card Clearing',
        'mastercard': 'Credit Card Clearing',
        'visa': 'Credit Card Clearing',
        'amex': 'Credit Card Clearing',
        'american express': 'Credit Card Clearing',
        'affiliate': 'Affiliate Receivable',
        'cash': 'Cash - Operating',
        'check': 'Undeposited Funds',
        'cheque': 'Undeposited Funds',
        'bank transfer': 'Bank Transfer Clearing',
        'wire transfer': 'Bank Transfer Clearing',
        'paypal': 'PayPal Clearing',
        'square': 'Square Clearing',
        'stripe': 'Stripe Clearing',
        'gift card': 'Gift Card Liability',
        'voucher': 'Voucher Clearing',
        'comp': 'Complimentary Services',
        'comped': 'Complimentary Services',
        'refund': 'Refunds Payable'
    }
    
    # Check for exact matches first
    if payment_type_lower in account_mapping:
        return account_mapping[payment_type_lower]
    
    # Check for partial matches
    for key, account in account_mapping.items():
        if key in payment_type_lower:
            return account
    
    # Default fallback
    return 'Accounts Receivable'

def create_payment_affiliate_breakdown(df):
    """Create detailed payment type and affiliate breakdown analysis"""
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 1.5rem; border-radius: 10px; margin-bottom: 2rem;">
        <h3 style="margin: 0 0 1rem 0; color: #2c3e50;">📈 Payment Type & Affiliate Analysis</h3>
        <p style="margin: 0; color: #6c757d;">Detailed breakdown of revenue by payment methods and affiliate relationships</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 1. AFFILIATE PAYMENT TYPE REVENUE (PAID/UNPAID) BY TOUR
    st.subheader("🤝 Affiliate Revenue Analysis by Tour")
    affiliate_analysis = create_affiliate_revenue_analysis(df)
    if not affiliate_analysis.empty:
        st.dataframe(
            affiliate_analysis,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tour Name": st.column_config.TextColumn("Tour Name", width="medium"),
                "Total Affiliate Revenue (Ex-Tax)": st.column_config.TextColumn("Affiliate Rev (Ex-Tax)", width="medium"),
                "Total Affiliate Revenue (Inc-Tax)": st.column_config.TextColumn("Affiliate Rev (Inc-Tax)", width="medium"),
                "Paid to Affiliate": st.column_config.TextColumn("Paid", width="small"),
                "Receivable from Affiliate": st.column_config.TextColumn("Receivable", width="small"),
                "Net Affiliate Position": st.column_config.TextColumn("Net Position", width="small"),
            }
        )
    else:
        st.info("💡 No affiliate payment data found in the selected records.")
    
    st.markdown("---")
    
    # 2. NON-AFFILIATE REVENUE BY TOUR
    st.subheader("🎯 Non-Affiliate Revenue by Tour")
    non_affiliate_revenue = create_non_affiliate_revenue_analysis(df)
    if not non_affiliate_revenue.empty:
        st.dataframe(
            non_affiliate_revenue,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tour Name": st.column_config.TextColumn("Tour Name", width="medium"),
                "Non-Affiliate Revenue (Ex-Tax)": st.column_config.TextColumn("Revenue (Ex-Tax)", width="medium"),
                "Non-Affiliate Revenue (Inc-Tax)": st.column_config.TextColumn("Revenue (Inc-Tax)", width="medium"),
                "Guest Count": st.column_config.TextColumn("Guests", width="small"),
                "Booking Count": st.column_config.TextColumn("Bookings", width="small"),
            }
        )
    else:
        st.info("💡 No non-affiliate revenue data found.")
    
    st.markdown("---")
    
    # 3. PAYMENT TYPE REVENUE AND REFUNDS BY TOUR
    st.subheader("💳 Payment Type Analysis by Tour")
    payment_type_analysis = create_payment_type_analysis(df)
    if not payment_type_analysis.empty:
        st.dataframe(
            payment_type_analysis,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tour Name": st.column_config.TextColumn("Tour Name", width="medium"),
                "Payment Type": st.column_config.TextColumn("Payment Type", width="small"),
                "Revenue (Ex-Tax)": st.column_config.TextColumn("Revenue (Ex-Tax)", width="medium"),
                "Revenue (Inc-Tax)": st.column_config.TextColumn("Revenue (Inc-Tax)", width="medium"),
                "Refunds (Ex-Tax)": st.column_config.TextColumn("Refunds (Ex-Tax)", width="medium"),
                "Refunds (Inc-Tax)": st.column_config.TextColumn("Refunds (Inc-Tax)", width="medium"),
                "Net (Ex-Tax)": st.column_config.TextColumn("Net (Ex-Tax)", width="medium"),
            }
        )
    else:
        st.info("💡 No payment type data available.")
    
    st.markdown("---")
    
    # 4. NON-AFFILIATE REFUNDS BY TOUR
    st.subheader("↩️ Non-Affiliate Refunds by Tour")
    non_affiliate_refunds = create_non_affiliate_refund_analysis(df)
    if not non_affiliate_refunds.empty:
        st.dataframe(
            non_affiliate_refunds,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tour Name": st.column_config.TextColumn("Tour Name", width="medium"),
                "Refunds (Ex-Tax)": st.column_config.TextColumn("Refunds (Ex-Tax)", width="medium"),
                "Refunds (Inc-Tax)": st.column_config.TextColumn("Refunds (Inc-Tax)", width="medium"),
                "Refund Count": st.column_config.TextColumn("Refund Count", width="small"),
            }
        )
    else:
        st.info("💡 No non-affiliate refund data found.")
    
    # EXPORT FUNCTIONALITY
    st.markdown("---")
    st.subheader("📥 Export Breakdown Data")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📊 Export Affiliate Analysis", help="Download affiliate analysis as CSV"):
            if not affiliate_analysis.empty:
                csv = affiliate_analysis.to_csv(index=False)
                st.download_button(
                    label="💾 Download CSV",
                    data=csv,
                    file_name=f"affiliate_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime='text/csv'
                )
    
    with col2:
        if st.button("🎯 Export Non-Affiliate Revenue", help="Download non-affiliate revenue as CSV"):
            if not non_affiliate_revenue.empty:
                csv = non_affiliate_revenue.to_csv(index=False)
                st.download_button(
                    label="💾 Download CSV",
                    data=csv,
                    file_name=f"non_affiliate_revenue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime='text/csv'
                )
    
    with col3:
        if st.button("💳 Export Payment Type Analysis", help="Download payment type analysis as CSV"):
            if not payment_type_analysis.empty:
                csv = payment_type_analysis.to_csv(index=False)
                st.download_button(
                    label="💾 Download CSV",
                    data=csv,
                    file_name=f"payment_type_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime='text/csv'
                )
    
    with col4:
        if st.button("↩️ Export Refunds Analysis", help="Download refunds analysis as CSV"):
            if not non_affiliate_refunds.empty:
                csv = non_affiliate_refunds.to_csv(index=False)
                st.download_button(
                    label="💾 Download CSV",
                    data=csv,
                    file_name=f"refunds_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime='text/csv'
                )

def create_affiliate_revenue_analysis(df):
    """Create affiliate payment analysis with paid/unpaid breakdown"""
    try:
        # Filter for affiliate payments only
        affiliate_df = df[df['Payment Type'].str.lower().str.contains('affiliate', na=False)].copy()
        
        if affiliate_df.empty:
            return pd.DataFrame()
        
        # Group by tour and calculate affiliate metrics
        affiliate_summary = affiliate_df.groupby('Item').agg({
            'Subtotal': 'sum',  # Ex-tax amount
            'Total': 'sum',     # Including tax
            'Total Paid': 'sum',
            'Receivable from Affiliate': 'sum',
            'Received from Affiliate': 'sum',
            '# of Pax': 'sum'
        }).reset_index()
        
        # Calculate net affiliate position
        affiliate_summary['Net Affiliate Position'] = affiliate_summary['Received from Affiliate'] - affiliate_summary['Receivable from Affiliate']
        
        # Format for display
        display_df = affiliate_summary.copy()
        display_df.rename(columns={
            'Item': 'Tour Name',
            'Subtotal': 'Total Affiliate Revenue (Ex-Tax)',
            'Total': 'Total Affiliate Revenue (Inc-Tax)',
            'Receivable from Affiliate': 'Receivable from Affiliate',
            'Received from Affiliate': 'Paid to Affiliate'
        }, inplace=True)
        
        # Format currency columns
        currency_cols = ['Total Affiliate Revenue (Ex-Tax)', 'Total Affiliate Revenue (Inc-Tax)', 
                        'Paid to Affiliate', 'Receivable from Affiliate', 'Net Affiliate Position']
        
        for col in currency_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "$0.00")
        
        # Select and reorder columns
        final_columns = ['Tour Name', 'Total Affiliate Revenue (Ex-Tax)', 'Total Affiliate Revenue (Inc-Tax)', 
                        'Paid to Affiliate', 'Receivable from Affiliate', 'Net Affiliate Position']
        display_df = display_df[final_columns]
        
        return display_df
        
    except Exception as e:
        st.error(f"❌ Error creating affiliate analysis: {str(e)}")
        return pd.DataFrame()

def create_non_affiliate_revenue_analysis(df):
    """Create revenue analysis excluding affiliate payments"""
    try:
        # Filter out affiliate payments
        non_affiliate_df = df[~df['Payment Type'].str.lower().str.contains('affiliate', na=False)].copy()
        
        if non_affiliate_df.empty:
            return pd.DataFrame()
        
        # Group by tour and calculate metrics
        revenue_summary = non_affiliate_df.groupby('Item').agg({
            'Subtotal': 'sum',      # Ex-tax amount
            'Total': 'sum',         # Including tax
            '# of Pax': 'sum'
        }).reset_index()
        
        # Add booking count
        booking_counts = non_affiliate_df.groupby('Item').size().reset_index(name='Booking Count')
        revenue_summary = revenue_summary.merge(booking_counts, on='Item', how='left')
        
        # Format for display
        display_df = revenue_summary.copy()
        display_df.rename(columns={
            'Item': 'Tour Name',
            'Subtotal': 'Non-Affiliate Revenue (Ex-Tax)',
            'Total': 'Non-Affiliate Revenue (Inc-Tax)',
            '# of Pax': 'Guest Count'
        }, inplace=True)
        
        # Format currency columns
        currency_cols = ['Non-Affiliate Revenue (Ex-Tax)', 'Non-Affiliate Revenue (Inc-Tax)']
        for col in currency_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "$0.00")
        
        # Format integer columns
        display_df['Guest Count'] = display_df['Guest Count'].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "0")
        display_df['Booking Count'] = display_df['Booking Count'].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "0")
        
        return display_df
        
    except Exception as e:
        st.error(f"❌ Error creating non-affiliate revenue analysis: {str(e)}")
        return pd.DataFrame()

def create_payment_type_analysis(df):
    """Create payment type revenue and refund analysis by tour"""
    try:
        # Separate revenue and refunds
        revenue_df = df[df['Payment or Refund'] == 'Payment'].copy() if 'Payment or Refund' in df.columns else df.copy()
        refund_df = df[df['Payment or Refund'] == 'Refund'].copy() if 'Payment or Refund' in df.columns else pd.DataFrame()
        
        # Group revenue by tour and payment type
        if not revenue_df.empty:
            revenue_summary = revenue_df.groupby(['Item', 'Payment Type']).agg({
                'Subtotal': 'sum',      # Ex-tax
                'Total': 'sum',         # Including tax
            }).reset_index()
        else:
            revenue_summary = pd.DataFrame()
        
        # Group refunds by tour and payment type
        if not refund_df.empty:
            refund_summary = refund_df.groupby(['Item', 'Payment Type']).agg({
                'Subtotal': 'sum',      # Ex-tax (will be negative)
                'Total': 'sum',         # Including tax (will be negative)
            }).reset_index()
            # Make refunds positive for display
            refund_summary['Subtotal'] = refund_summary['Subtotal'].abs()
            refund_summary['Total'] = refund_summary['Total'].abs()
        else:
            refund_summary = pd.DataFrame()
        
        # Combine revenue and refunds
        if not revenue_summary.empty:
            combined_df = revenue_summary.copy()
            combined_df['Revenue_Subtotal'] = combined_df['Subtotal']
            combined_df['Revenue_Total'] = combined_df['Total']
            combined_df['Refund_Subtotal'] = 0.0
            combined_df['Refund_Total'] = 0.0
            
            # Merge refunds
            if not refund_summary.empty:
                for _, refund_row in refund_summary.iterrows():
                    mask = (combined_df['Item'] == refund_row['Item']) & (combined_df['Payment Type'] == refund_row['Payment Type'])
                    if mask.any():
                        combined_df.loc[mask, 'Refund_Subtotal'] = float(refund_row['Subtotal'])
                        combined_df.loc[mask, 'Refund_Total'] = float(refund_row['Total'])
            
            # Calculate net amounts
            combined_df['Net_Subtotal'] = combined_df['Revenue_Subtotal'] - combined_df['Refund_Subtotal']
            combined_df['Net_Total'] = combined_df['Revenue_Total'] - combined_df['Refund_Total']
            
            # Format for display
            display_df = combined_df.copy()
            display_df.rename(columns={
                'Item': 'Tour Name',
                'Revenue_Subtotal': 'Revenue (Ex-Tax)',
                'Revenue_Total': 'Revenue (Inc-Tax)',
                'Refund_Subtotal': 'Refunds (Ex-Tax)',
                'Refund_Total': 'Refunds (Inc-Tax)',
                'Net_Subtotal': 'Net (Ex-Tax)',
                'Net_Total': 'Net (Inc-Tax)'
            }, inplace=True)
            
            # Format currency columns
            currency_cols = ['Revenue (Ex-Tax)', 'Revenue (Inc-Tax)', 'Refunds (Ex-Tax)', 
                            'Refunds (Inc-Tax)', 'Net (Ex-Tax)', 'Net (Inc-Tax)']
            
            for col in currency_cols:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "$0.00")
            
            # Select final columns
            final_columns = ['Tour Name', 'Payment Type', 'Revenue (Ex-Tax)', 'Revenue (Inc-Tax)', 
                            'Refunds (Ex-Tax)', 'Refunds (Inc-Tax)', 'Net (Ex-Tax)']
            display_df = display_df[final_columns]
            
            return display_df
        
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"❌ Error creating payment type analysis: {str(e)}")
        return pd.DataFrame()

def create_non_affiliate_refund_analysis(df):
    """Create refund analysis excluding affiliate payments"""
    try:
        # Filter for refunds only, excluding affiliates
        refund_df = df[
            (df['Payment or Refund'] == 'Refund') & 
            (~df['Payment Type'].str.lower().str.contains('affiliate', na=False))
        ].copy() if 'Payment or Refund' in df.columns else pd.DataFrame()
        
        if refund_df.empty:
            return pd.DataFrame()
        
        # Group by tour
        refund_summary = refund_df.groupby('Item').agg({
            'Subtotal': 'sum',      # Ex-tax (will be negative)
            'Total': 'sum',         # Including tax (will be negative)
        }).reset_index()
        
        # Make refunds positive and add refund count
        refund_summary['Subtotal'] = refund_summary['Subtotal'].abs()
        refund_summary['Total'] = refund_summary['Total'].abs()
        
        # Add refund transaction count
        refund_counts = refund_df.groupby('Item').size().reset_index(name='Refund Count')
        refund_summary = refund_summary.merge(refund_counts, on='Item', how='left')
        
        # Format for display
        display_df = refund_summary.copy()
        display_df.rename(columns={
            'Item': 'Tour Name',
            'Subtotal': 'Refunds (Ex-Tax)',
            'Total': 'Refunds (Inc-Tax)'
        }, inplace=True)
        
        # Format currency columns
        currency_cols = ['Refunds (Ex-Tax)', 'Refunds (Inc-Tax)']
        for col in currency_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "$0.00")
        
        # Format refund count
        display_df['Refund Count'] = display_df['Refund Count'].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "0")
        
        return display_df
        
    except Exception as e:
        st.error(f"❌ Error creating refund analysis: {str(e)}")
        return pd.DataFrame()

def display_pivot_table(pivot_df):
    """Display the pivot table with nice formatting"""
    try:
        # Keep original numeric data for calculations
        original_df = pivot_df.copy()
        
        # Format numeric columns for display
        display_df = pivot_df.copy()
        
        # Format currency columns
        currency_columns = ['Total Revenue', 'Gross Payments', 'Total Refunds', 'Net Revenue', 
                           'Receivable from Affiliate', 'Received from Affiliate', 'Net After Refunds', 'Revenue per Guest',
                           'Subtotal (Ex-Tax)', 'Total Fees per Person', 'Total Fee Revenue', 'Tour Revenue (Net of Fees)']
        
        for col in currency_columns:
            if col in display_df.columns:
                # Ensure the column is numeric before formatting
                display_df[col] = pd.to_numeric(display_df[col], errors='coerce').fillna(0)
                display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "$0.00")
        
        # Format integer columns
        integer_columns = ['Total Guests', 'Booking Count']
        for col in integer_columns:
            if col in display_df.columns:
                # Ensure the column is numeric before formatting
                display_df[col] = pd.to_numeric(display_df[col], errors='coerce').fillna(0)
                display_df[col] = display_df[col].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "0")
        
        # Display the table
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tour Name": st.column_config.TextColumn("Tour Name", width="medium"),
                "Total Guests": st.column_config.TextColumn("Total Guests", width="small"),
                "Booking Count": st.column_config.TextColumn("Bookings", width="small"),
                "Subtotal (Ex-Tax)": st.column_config.TextColumn("Subtotal (Ex-Tax)", width="medium"),
                "Total Fee Revenue": st.column_config.TextColumn("Fee Revenue", width="medium"),
                "Tour Revenue (Net of Fees)": st.column_config.TextColumn("Tour Revenue", width="medium"),
                "Total Refunds": st.column_config.TextColumn("Total Refunds", width="medium"),
                "Receivable from Affiliate": st.column_config.TextColumn("Affiliate Due", width="medium"),
                "Received from Affiliate": st.column_config.TextColumn("Affiliate Paid", width="medium"),
                "Fee Details": st.column_config.TextColumn("Fee Breakdown", width="large"),
            }
        )
        
        # Summary statistics using original numeric data
        st.markdown("### 📈 Summary Statistics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_tours = len(original_df)
            st.metric("Total Tours", total_tours)
        
        with col2:
            if 'Total Guests' in original_df.columns:
                total_guests = pd.to_numeric(original_df['Total Guests'], errors='coerce').fillna(0).sum()
                st.metric("Total Guests", f"{int(total_guests):,}")
        
        with col3:
            if 'Total Revenue' in original_df.columns:
                total_revenue = pd.to_numeric(original_df['Total Revenue'], errors='coerce').fillna(0).sum()
                st.metric("Total Revenue", f"${total_revenue:,.2f}")
        
        with col4:
            if 'Total Refunds' in original_df.columns:
                total_refunds = pd.to_numeric(original_df['Total Refunds'], errors='coerce').fillna(0).sum()
                st.metric("Total Refunds", f"${total_refunds:,.2f}")
        
    except Exception as e:
        st.error(f"❌ Error displaying pivot table: {str(e)}")
        st.error(f"Debug info: Columns in pivot_df: {list(pivot_df.columns)}")
        st.error(f"Data types: {pivot_df.dtypes.to_dict()}")
        # Fallback to basic display
        st.dataframe(pivot_df, use_container_width=True)

def quickbooks_mappings_page():
    """QuickBooks Account Mappings Page"""
    st.title("🔗 QuickBooks Account Mappings")

    # Compact CSS
    st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {gap: 4px; margin-bottom: 1rem;}
    .stTabs [data-baseweb="tab"] {padding: 8px 16px; font-size: 0.9rem;}
    </style>
    """, unsafe_allow_html=True)
    
    # File upload for populating dropdowns
    st.sidebar.header("📁 Data Source")
    csv_file = st.sidebar.file_uploader(
        "Upload Sales CSV to populate mappings",
        type=['csv'],
        help="Upload FareHarbour sales report to extract tours and payment types"
    )
    
    # Initialize session state for mappings if not exists
    if 'qb_mappings_data' not in st.session_state:
        st.session_state.qb_mappings_data = load_quickbooks_mappings()
    
    # Create tabs for different mapping types
    tab1, tab2, tab3 = st.tabs(["🎪 Tour Revenue Mappings", "💰 Fee Revenue Mappings", "💳 Payment Type Mappings"])
    
    # Extract data from CSV if uploaded
    tours_list, fees_list, payment_types_list = [], [], []
    if csv_file is not None:
        df = load_sales_csv_data(csv_file)
        if df is not None and not df.empty:
            tours_list, fees_list, payment_types_list = extract_mapping_items(df)
    
    with tab1:
        st.subheader("🎪 Tour Revenue Mappings")
        create_tour_revenue_mappings_table(tours_list)

    with tab2:
        st.subheader("💰 Fee Revenue Mappings")
        create_fee_revenue_mappings_table(fees_list)

    with tab3:
        st.subheader("💳 Payment Type Mappings")
        create_payment_type_mappings_table(payment_types_list)
    
    # Global save/reset actions
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("💾 Save All Mappings", type="primary", help="Save all mappings to database"):
            save_result = save_all_mappings()
            if save_result:
                st.success("✅ All mappings saved successfully!")
                st.session_state.qb_mappings_data = load_quickbooks_mappings()  # Refresh data
                st.rerun()
            else:
                st.error("❌ Error saving mappings. Please try again.")
    
    with col2:
        if st.button("🔄 Refresh from Database", help="Reload mappings from database"):
            st.session_state.qb_mappings_data = load_quickbooks_mappings()
            st.success("✅ Mappings refreshed from database!")
            st.rerun()
    
    with col3:
        if st.button("📊 View Mapping Summary", help="Show summary of current mappings"):
            show_mapping_summary()

def extract_mapping_items(df):
    """Extract unique tours, fees, and payment types from CSV data"""
    try:
        # Extract unique tours
        tours_list = sorted(df['Item'].dropna().unique().tolist()) if 'Item' in df.columns else []
        
        # Extract fees from database (since fees are managed there)
        fees_query = execute_query("SELECT DISTINCT name FROM fees ORDER BY name")
        fees_list = [fee[0] for fee in fees_query] if fees_query else []
        
        # Extract unique payment types
        payment_types_list = sorted(df['Payment Type'].dropna().unique().tolist()) if 'Payment Type' in df.columns else []
        
        return tours_list, fees_list, payment_types_list
        
    except Exception as e:
        st.error(f"❌ Error extracting mapping items: {str(e)}")
        return [], [], []

def get_quickbooks_accounts():
    """Get QuickBooks account list (placeholder for API integration)"""
    # Placeholder accounts - will be replaced with QB API data later
    accounts = {
        'Revenue Accounts': [
            'Tour Revenue - General',
            'Tour Revenue - Whale Watching', 
            'Tour Revenue - Bear Watching',
            'Tour Revenue - Hot Springs',
            'Fee Revenue - Park Fees',
            'Fee Revenue - Fuel Surcharge',
            'Fee Revenue - Stewardship',
            'Other Revenue'
        ],
        'Asset Accounts': [
            'Cash - Operating',
            'Cash - Savings',
            'Undeposited Funds',
            'Accounts Receivable',
            'Credit Card Clearing',
            'PayPal Clearing',
            'Square Clearing',
            'Stripe Clearing'
        ],
        'Liability Accounts': [
            'Accounts Payable - Affiliates',
            'Gift Card Liability',
            'Voucher Clearing',
            'Refunds Payable'
        ]
    }
    
    # Flatten for dropdown use
    all_accounts = []
    for category, account_list in accounts.items():
        all_accounts.extend(account_list)
    
    return sorted(all_accounts)

def create_tour_revenue_mappings_table(tours_list):
    """Create editable table for tour to revenue account mappings"""
    existing_mappings = {
        mapping['fareharbour_item']: mapping
        for mapping in st.session_state.qb_mappings_data
        if mapping['mapping_type'] == 'tour_revenue'
    }

    qb_accounts = get_quickbooks_accounts()
    revenue_accounts = [acc for acc in qb_accounts if 'Revenue' in acc]

    if not tours_list:
        st.info("💡 Upload a sales CSV to populate tour mappings automatically.")
        return

    mappings_data = []
    for tour in tours_list:
        existing = existing_mappings.get(tour, {})
        mappings_data.append({
            'Tour Name': tour,
            'QuickBooks Account': existing.get('quickbooks_account', ''),
            'Status': 'Mapped' if existing else 'Unmapped'
        })

    if mappings_data:
        edited_df = st.data_editor(
            pd.DataFrame(mappings_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tour Name": st.column_config.TextColumn("Tour Name", disabled=True, width="medium"),
                "QuickBooks Account": st.column_config.SelectboxColumn(
                    "QuickBooks Account", options=revenue_accounts, width="large"
                ),
                "Status": st.column_config.TextColumn("Status", disabled=True, width="small")
            },
            key="tour_mappings_editor"
        )

        for idx, row in edited_df.iterrows():
            tour_name = row['Tour Name']
            qb_account = row['QuickBooks Account']

            mapping = {
                'mapping_type': 'tour_revenue',
                'fareharbour_item': tour_name,
                'quickbooks_account': qb_account,
                'account_type': 'revenue'
            }

            update_session_mapping(mapping)

def create_fee_revenue_mappings_table(fees_list):
    """Create editable table for fee to revenue account mappings"""
    existing_mappings = {
        mapping['fareharbour_item']: mapping
        for mapping in st.session_state.qb_mappings_data
        if mapping['mapping_type'] == 'fee_revenue'
    }

    qb_accounts = get_quickbooks_accounts()
    revenue_accounts = [acc for acc in qb_accounts if 'Revenue' in acc or 'Fee' in acc]

    if not fees_list:
        st.info("💡 Add fees in Tours & Fees Management to create fee mappings.")
        return

    mappings_data = []
    for fee in fees_list:
        existing = existing_mappings.get(fee, {})
        mappings_data.append({
            'Fee Name': fee,
            'QuickBooks Account': existing.get('quickbooks_account', ''),
            'Status': 'Mapped' if existing else 'Unmapped'
        })

    if mappings_data:
        edited_df = st.data_editor(
            pd.DataFrame(mappings_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fee Name": st.column_config.TextColumn("Fee Name", disabled=True, width="medium"),
                "QuickBooks Account": st.column_config.SelectboxColumn(
                    "QuickBooks Account", options=revenue_accounts, width="large"
                ),
                "Status": st.column_config.TextColumn("Status", disabled=True, width="small")
            },
            key="fee_mappings_editor"
        )

        for idx, row in edited_df.iterrows():
            fee_name = row['Fee Name']
            qb_account = row['QuickBooks Account']

            mapping = {
                'mapping_type': 'fee_revenue',
                'fareharbour_item': fee_name,
                'quickbooks_account': qb_account,
                'account_type': 'revenue'
            }

            update_session_mapping(mapping)

def create_payment_type_mappings_table(payment_types_list):
    """Create editable table for payment type to bank/clearing account mappings"""
    existing_mappings = {
        mapping['fareharbour_item']: mapping
        for mapping in st.session_state.qb_mappings_data
        if mapping['mapping_type'] == 'payment_type'
    }

    qb_accounts = get_quickbooks_accounts()
    asset_accounts = [acc for acc in qb_accounts if any(word in acc for word in ['Cash', 'Clearing', 'Receivable', 'Undeposited'])]

    if not payment_types_list:
        st.info("💡 Upload a sales CSV to populate payment type mappings automatically.")
        return

    mappings_data = []
    for payment_type in payment_types_list:
        existing = existing_mappings.get(payment_type, {})
        mappings_data.append({
            'Payment Type': payment_type,
            'QuickBooks Account': existing.get('quickbooks_account', ''),
            'Status': 'Mapped' if existing else 'Unmapped'
        })

    if mappings_data:
        edited_df = st.data_editor(
            pd.DataFrame(mappings_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Payment Type": st.column_config.TextColumn("Payment Type", disabled=True, width="medium"),
                "QuickBooks Account": st.column_config.SelectboxColumn(
                    "QuickBooks Account", options=asset_accounts, width="large"
                ),
                "Status": st.column_config.TextColumn("Status", disabled=True, width="small")
            },
            key="payment_mappings_editor"
        )

        for idx, row in edited_df.iterrows():
            payment_type = row['Payment Type']
            qb_account = row['QuickBooks Account']

            mapping = {
                'mapping_type': 'payment_type',
                'fareharbour_item': payment_type,
                'quickbooks_account': qb_account,
                'account_type': 'asset'
            }

            update_session_mapping(mapping)

def update_session_mapping(mapping):
    """Update mapping in session state"""
    # Find existing mapping or add new one
    mapping_key = f"{mapping['mapping_type']}_{mapping['fareharbour_item']}"
    
    # Update existing or add new
    existing_index = None
    for i, existing in enumerate(st.session_state.qb_mappings_data):
        if (existing['mapping_type'] == mapping['mapping_type'] and 
            existing['fareharbour_item'] == mapping['fareharbour_item']):
            existing_index = i
            break
    
    if existing_index is not None:
        st.session_state.qb_mappings_data[existing_index].update(mapping)
    else:
        st.session_state.qb_mappings_data.append(mapping)

def load_quickbooks_mappings():
    """Load QuickBooks mappings from database"""
    try:
        mappings = execute_query("""
            SELECT mapping_type, fareharbour_item, quickbooks_account, account_type, is_active
            FROM quickbooks_mappings 
            WHERE is_active = true
            ORDER BY mapping_type, fareharbour_item
        """)
        
        if mappings:
            return [
                {
                    'mapping_type': mapping[0],
                    'fareharbour_item': mapping[1], 
                    'quickbooks_account': mapping[2],
                    'account_type': mapping[3],
                    'is_active': mapping[4]
                }
                for mapping in mappings
            ]
        else:
            return []
            
    except Exception as e:
        st.error(f"❌ Error loading QuickBooks mappings: {str(e)}")
        return []

def save_all_mappings():
    """Save all mappings to database"""
    try:
        # First, deactivate all existing mappings
        execute_query("UPDATE quickbooks_mappings SET is_active = false, updated_at = CURRENT_TIMESTAMP")
        
        # Insert or update mappings
        success_count = 0
        for mapping in st.session_state.qb_mappings_data:
            if mapping.get('quickbooks_account'):  # Only save if QB account is selected
                # Try to update existing record first
                result = execute_query("""
                    UPDATE quickbooks_mappings 
                    SET quickbooks_account = :qb_account, 
                        account_type = :account_type,
                        is_active = true,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE mapping_type = :mapping_type 
                    AND fareharbour_item = :fh_item
                """, {
                    'qb_account': mapping['quickbooks_account'],
                    'account_type': mapping['account_type'],
                    'mapping_type': mapping['mapping_type'],
                    'fh_item': mapping['fareharbour_item']
                })
                
                # If no rows updated, insert new record
                if result is not None:
                    # Check if update affected any rows by trying insert
                    execute_query("""
                        INSERT INTO quickbooks_mappings (mapping_type, fareharbour_item, quickbooks_account, account_type)
                        VALUES (:mapping_type, :fh_item, :qb_account, :account_type)
                        ON CONFLICT (mapping_type, fareharbour_item) DO UPDATE SET
                        quickbooks_account = EXCLUDED.quickbooks_account,
                        account_type = EXCLUDED.account_type,
                        is_active = true,
                        updated_at = CURRENT_TIMESTAMP
                    """, {
                        'mapping_type': mapping['mapping_type'],
                        'fh_item': mapping['fareharbour_item'],
                        'qb_account': mapping['quickbooks_account'],
                        'account_type': mapping['account_type']
                    })
                    success_count += 1
        
        return success_count > 0
        
    except Exception as e:
        st.error(f"❌ Error saving mappings: {str(e)}")
        return False

def show_mapping_summary():
    """Show summary of current mappings"""
    if not st.session_state.qb_mappings_data:
        st.info("💡 No mappings configured yet.")
        return
    
    # Group by mapping type
    tour_mappings = [m for m in st.session_state.qb_mappings_data if m['mapping_type'] == 'tour_revenue' and m.get('quickbooks_account')]
    fee_mappings = [m for m in st.session_state.qb_mappings_data if m['mapping_type'] == 'fee_revenue' and m.get('quickbooks_account')]
    payment_mappings = [m for m in st.session_state.qb_mappings_data if m['mapping_type'] == 'payment_type' and m.get('quickbooks_account')]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Tour Mappings", len(tour_mappings))
        if tour_mappings:
            with st.expander("View Tour Mappings"):
                for mapping in tour_mappings:
                    st.write(f"• {mapping['fareharbour_item']} → {mapping['quickbooks_account']}")
    
    with col2:
        st.metric("Fee Mappings", len(fee_mappings))
        if fee_mappings:
            with st.expander("View Fee Mappings"):
                for mapping in fee_mappings:
                    st.write(f"• {mapping['fareharbour_item']} → {mapping['quickbooks_account']}")
    
    with col3:
        st.metric("Payment Mappings", len(payment_mappings))
        if payment_mappings:
            with st.expander("View Payment Mappings"):
                for mapping in payment_mappings:
                    st.write(f"• {mapping['fareharbour_item']} → {mapping['quickbooks_account']}")

def main():
    st.title("🔍 FareHarbour - QuickBooks Reconciliation Tool")
    st.markdown("Upload your FareHarbour CSV and QuickBooks Excel files to compare bookings and identify discrepancies.")
    
    # Add navigation in sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Select Page", ["Reconciliation", "Tours & Fees Management", "Sales Report Analysis", "QuickBooks Mappings"])
    
    if page == "Tours & Fees Management":
        manage_tours_and_fees()
        return
    elif page == "Sales Report Analysis":
        sales_report_analysis()
        return
    elif page == "QuickBooks Mappings":
        quickbooks_mappings_page()
        return
    
    # Sidebar for file uploads
    st.sidebar.header("📁 File Upload")
    
    fh_file = st.sidebar.file_uploader(
        "Upload FareHarbour Bookings CSV",
        type=['csv'],
        help="Upload the bookings report CSV from FareHarbour"
    )
    
    fh_payments_file = st.sidebar.file_uploader(
        "Upload FareHarbour Payments CSV",
        type=['csv'],
        help="Upload the payments/refunds report CSV from FareHarbour"
    )
    
    qb_file = st.sidebar.file_uploader(
        "Upload QuickBooks Excel",
        type=['xlsx', 'xls'],
        help="Upload the transaction list Excel from QuickBooks"
    )
    
    # Main content area
    if fh_file is not None and qb_file is not None:
        # Load data
        with st.spinner("Loading and processing data..."):
            fh_df = load_fareharbour_data(fh_file)
            qb_df = load_quickbooks_data(qb_file)
            
            # Load payments data if provided
            fh_payments_df = None
            if fh_payments_file is not None:
                fh_payments_df = load_fareharbour_payments_data(fh_payments_file)
        
        if fh_df is not None and qb_df is not None:
            # Display data overview
            if fh_payments_df is not None:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.subheader("📊 FareHarbour Data Overview")
                    st.metric("Total Bookings", len(fh_df))
                    st.metric("Paid Bookings", len(fh_df[fh_df['Is Paid']]))
                    st.metric("Cancelled Bookings", len(fh_df[fh_df['Is Cancelled']]))
                    st.metric("Total Revenue", f"${fh_df['Total Paid'].sum():,.2f}")
                
                with col2:
                    st.subheader("📋 QuickBooks Data Overview")
                    st.metric("Total Transactions", len(qb_df))
                    
                    # Safe handling of amount columns
                    if 'Net_Amount' in qb_df.columns:
                        total_amount = qb_df['Net_Amount'].fillna(0).sum()
                    elif 'Amount' in qb_df.columns:
                        total_amount = qb_df['Amount'].fillna(0).sum()
                    else:
                        total_amount = 0
                    
                    st.metric("Total Amount", f"${total_amount:,.2f}")
                    
                    # Safe handling of open balance
                    if 'Open_Balance' in qb_df.columns:
                        open_balance = qb_df['Open_Balance'].fillna(0).sum()
                    else:
                        open_balance = 0
                    
                    st.metric("Open Balance", f"${open_balance:,.2f}")
                    st.metric("Transactions with FH ID", len(qb_df[qb_df['FH_Booking_ID'].notna()]))
                
                with col3:
                    st.subheader("💳 FareHarbour Payments Overview")
                    st.metric("Total Transactions", len(fh_payments_df))
                    
                    if 'Is_Payment' in fh_payments_df.columns and 'Is_Refund' in fh_payments_df.columns:
                        payment_count = fh_payments_df['Is_Payment'].sum()
                        refund_count = fh_payments_df['Is_Refund'].sum()
                        st.metric("Payments", payment_count)
                        st.metric("Refunds", refund_count)
                    
                    if 'Net' in fh_payments_df.columns:
                        total_net = fh_payments_df['Net'].sum()
                        st.metric("Total Net Amount", f"${total_net:,.2f}")
            else:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📊 FareHarbour Data Overview")
                    st.metric("Total Bookings", len(fh_df))
                    st.metric("Paid Bookings", len(fh_df[fh_df['Is Paid']]))
                    st.metric("Cancelled Bookings", len(fh_df[fh_df['Is Cancelled']]))
                    st.metric("Total Revenue", f"${fh_df['Total Paid'].sum():,.2f}")
                
                with col2:
                    st.subheader("📋 QuickBooks Data Overview")
                    st.metric("Total Transactions", len(qb_df))
                    
                    # Safe handling of amount columns
                    if 'Net_Amount' in qb_df.columns:
                        total_amount = qb_df['Net_Amount'].fillna(0).sum()
                    elif 'Amount' in qb_df.columns:
                        total_amount = qb_df['Amount'].fillna(0).sum()
                    else:
                        total_amount = 0
                    
                    st.metric("Total Amount", f"${total_amount:,.2f}")
                    
                    # Safe handling of open balance
                    if 'Open_Balance' in qb_df.columns:
                        open_balance = qb_df['Open_Balance'].fillna(0).sum()
                    else:
                        open_balance = 0
                    
                    st.metric("Open Balance", f"${open_balance:,.2f}")
                    st.metric("Transactions with FH ID", len(qb_df[qb_df['FH_Booking_ID'].notna()]))
            
            # Reconciliation Analysis
            st.header("🔍 Reconciliation Analysis")
            
            # Tab layout for different analyses
            if fh_payments_df is not None:
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "📋 Missing Bookings", 
                    "❌ Cancelled vs Open", 
                    "💰 Amount Differences",
                    "💳 Payment/Refund Comparison",
                    "📈 Summary Report"
                ])
            else:
                tab1, tab2, tab3, tab4 = st.tabs([
                    "📋 Missing Bookings", 
                    "❌ Cancelled vs Open", 
                    "💰 Amount Differences", 
                    "📈 Summary Report"
                ])
            
            with tab1:
                st.subheader("Bookings in FareHarbour but Missing in QuickBooks")
                missing_bookings = find_missing_bookings(fh_df, qb_df)
                
                if not missing_bookings.empty:
                    st.warning(f"Found {len(missing_bookings)} missing bookings")
                    
                    # Load existing notes for missing bookings
                    missing_notes_file = "missing_bookings_notes.csv"
                    existing_missing_notes = load_notes_from_csv(missing_notes_file)
                    
                    # Merge notes with missing bookings data
                    missing_bookings_with_notes = merge_notes_with_data(missing_bookings, existing_missing_notes, 'Booking ID Clean')
                    
                    # Create notes editor
                    edited_missing_df, display_cols = create_notes_editor(
                        missing_bookings_with_notes, 
                        "Missing Bookings", 
                        "missing"
                    )
                    
                    # Save and export buttons
                    col_save, col_export = st.columns(2)
                    
                    with col_save:
                        if st.button("💾 Save Missing Bookings Notes", type="primary", key="save_missing_notes"):
                            if save_table_notes(edited_missing_df, missing_notes_file, "Missing Bookings"):
                                st.rerun()
                    
                    with col_export:
                        if st.button("📥 Export Missing Bookings", key="export_missing"):
                            excel_data = export_to_excel({
                                "Missing_Bookings": edited_missing_df,
                                "Missing_Bookings_All_Columns": missing_bookings_with_notes
                            })
                            st.download_button(
                                label="Download Excel",
                                data=excel_data,
                                file_name=f"missing_bookings_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    
                    # Show notes statistics
                    non_empty_notes = edited_missing_df['Notes'].fillna('').str.strip().ne('').sum() if 'Notes' in edited_missing_df.columns else 0
                    st.markdown(f"""
                    **Notes Statistics:** {non_empty_notes} missing bookings have notes out of {len(edited_missing_df)} total
                    """)
                    
                    # Show notes file info
                    show_notes_file_info(missing_notes_file, "Missing Bookings", existing_missing_notes)
                    
                else:
                    st.success("✅ No missing bookings found!")
            
            with tab2:
                st.subheader("Cancelled in FareHarbour but Open in QuickBooks")
                cancelled_vs_open = find_cancelled_vs_open(fh_df, qb_df)
                
                if not cancelled_vs_open.empty:
                    st.error(f"Found {len(cancelled_vs_open)} discrepancies")
                    
                    # Load existing notes for cancelled vs open
                    cancelled_notes_file = "cancelled_vs_open_notes.csv"
                    existing_cancelled_notes = load_notes_from_csv(cancelled_notes_file)
                    
                    # Merge notes with cancelled vs open data
                    cancelled_vs_open_with_notes = merge_notes_with_data(cancelled_vs_open, existing_cancelled_notes, 'Booking ID Clean')
                    
                    # Create notes editor
                    edited_cancelled_df, display_cols = create_notes_editor(
                        cancelled_vs_open_with_notes, 
                        "Cancelled vs Open", 
                        "cancelled"
                    )
                    
                    # Action buttons section
                    st.subheader("📋 Actions")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("💾 Save Cancelled vs Open Notes", type="primary", key="save_cancelled_notes"):
                            if save_table_notes(edited_cancelled_df, cancelled_notes_file, "Cancelled vs Open"):
                                st.rerun()
                    
                    with col2:
                        if st.button("📥 Export Cancelled vs Open", key="export_cancelled"):
                            excel_data = export_to_excel({
                                "Cancelled_vs_Open": edited_cancelled_df,
                                "Cancelled_vs_Open_All_Columns": cancelled_vs_open_with_notes
                            })
                            st.download_button(
                                label="Download Excel",
                                data=excel_data,
                                file_name=f"cancelled_vs_open_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    
                    with col3:
                        # Only show void feature if enabled
                        if ENABLE_VOID_FEATURE:
                            # Initialize session state for void process
                            if 'void_step' not in st.session_state:
                                st.session_state.void_step = 'ready'
                            
                            if st.session_state.void_step == 'ready':
                                if st.button("🗑️ Void All in QuickBooks", type="primary", key="void_button"):
                                    st.session_state.void_step = 'confirm'
                                    st.rerun()
                            
                            elif st.session_state.void_step == 'confirm':
                                st.warning("⚠️ This will void all open invoices in QuickBooks for the cancelled bookings shown above.")
                                
                                # Show what will be voided
                                doc_numbers = []
                                if '#' in cancelled_vs_open.columns:
                                    doc_numbers = cancelled_vs_open['#'].dropna().unique().tolist()
                                
                                if doc_numbers:
                                    st.info(f"📋 About to void {len(doc_numbers)} invoices: {', '.join(map(str, doc_numbers))}")
                                
                                col_confirm1, col_confirm2 = st.columns(2)
                                
                                with col_confirm1:
                                    if st.button("✅ Yes, Void All", type="primary", key="confirm_void"):
                                        st.session_state.void_step = 'processing'
                                        st.rerun()
                                
                                with col_confirm2:
                                    if st.button("❌ Cancel", key="cancel_void"):
                                        st.session_state.void_step = 'ready'
                                        st.rerun()
                            
                            elif st.session_state.void_step == 'processing':
                                st.info("🔄 Processing void requests...")
                                
                                # Show what will be voided
                                doc_numbers = []
                                if '#' in cancelled_vs_open.columns:
                                    doc_numbers = cancelled_vs_open['#'].dropna().unique().tolist()
                                
                                if doc_numbers:
                                    st.info(f"📋 Voiding {len(doc_numbers)} invoices: {', '.join(map(str, doc_numbers))}")
                                    
                                    # Execute the voiding
                                    with st.spinner("Voiding invoices in QuickBooks..."):
                                        void_results = void_invoices_in_quickbooks(cancelled_vs_open)
                                    
                                    # Show results summary
                                    if void_results["success"] > 0:
                                        st.success(f"✅ Successfully voided {void_results['success']} invoices")
                                    
                                    if void_results["failed"] > 0:
                                        st.error(f"❌ Failed to void {void_results['failed']} invoices")
                                    
                                    # Show detailed results
                                    with st.expander("📊 Detailed Results"):
                                        results_df = pd.DataFrame(void_results["results"])
                                        st.dataframe(results_df, use_container_width=True)
                                        
                                        # Option to download results
                                        if not results_df.empty:
                                            excel_results = export_to_excel({"Void_Results": results_df})
                                            st.download_button(
                                                label="📥 Download Void Results",
                                                data=excel_results,
                                                file_name=f"void_results_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                            )
                                    
                                    # Reset for next use
                                    if st.button("🔄 Reset", key="reset_void"):
                                        st.session_state.void_step = 'ready'
                                        st.rerun()
                                else:
                                    st.error("No document numbers found to void. Please ensure your QuickBooks data contains the '#' column with document numbers.")
                                    st.session_state.void_step = 'ready'
                        else:
                            st.info("🔒 Void feature disabled for security")
                    
                    # Information about the webhook
                    with st.expander("ℹ️ About the Void Process"):
                        st.markdown("""
                        **How it works:**
                        - Extracts document numbers from the QuickBooks data (# column)
                        - Calls your n8n webhook at `https://n8n.fintask.ie/webhook/void_inv` for each invoice
                        - Sends the document number as a parameter to the webhook
                        - Shows progress and results for each voiding operation
                        
                        **Webhook Payload Format:**
                        ```json
                        {
                            "doc_number": "INV-001",
                            "action": "void",
                            "source": "fareharbour_reconciliation"
                        }
                        ```
                        
                        **To get FH numbers in your n8n flow:**
                        1. The webhook receives the QB document number
                        2. Use the document number to query your QuickBooks API
                        3. Extract the FH booking ID from the invoice memo/description field
                        4. Use that FH booking ID for any additional processing needed
                        """)
                    
                    # Show notes statistics
                    non_empty_notes = edited_cancelled_df['Notes'].fillna('').str.strip().ne('').sum() if 'Notes' in edited_cancelled_df.columns else 0
                    st.markdown(f"""
                    **Notes Statistics:** {non_empty_notes} cancelled vs open issues have notes out of {len(edited_cancelled_df)} total
                    """)
                    
                    # Show notes file info
                    show_notes_file_info(cancelled_notes_file, "Cancelled vs Open", existing_cancelled_notes)
                
                else:
                    st.success("✅ No cancelled/open discrepancies found!")
            
            with tab3:
                st.subheader("💰 Amount Differences Between Systems")
                
                # Add explanation of comparison logic
                st.info("""
                **Comparison Logic:**
                - **Invoice Amounts**: FareHarbour 'Total' vs QuickBooks 'Amount'
                - **Tax Amounts**: FareHarbour 'Total Tax' vs QuickBooks 'Tax Amount'  
                - **Payment Status**: FareHarbour 'Amount Due' vs QuickBooks 'Open Balance'
                """)
                
                amount_diffs = compare_amounts(fh_df, qb_df)
                
                if not amount_diffs.empty:
                    st.warning(f"Found {len(amount_diffs)} bookings with amount discrepancies")
                    
                    # Load existing notes
                    existing_notes = load_notes_from_csv()
                    
                    # Merge notes with amount differences data
                    amount_diffs_with_notes = merge_notes_with_data(amount_diffs, existing_notes)
                    
                    # Special analysis for cancelled bookings
                    if 'Is_Cancelled' in amount_diffs.columns:
                        cancelled_diffs = amount_diffs[amount_diffs['Is_Cancelled'] == True]
                        if not cancelled_diffs.empty:
                            st.subheader("🚨 Cancelled Bookings Analysis")
                            st.info(f"Found {len(cancelled_diffs)} cancelled bookings with amount discrepancies")
                            
                            # Show cancelled bookings that don't have net 0 in QB
                            if 'QB_Amount' in cancelled_diffs.columns:
                                not_refunded = cancelled_diffs[abs(cancelled_diffs['QB_Amount']) > 0.01]
                                if not not_refunded.empty:
                                    st.error(f"⚠️ {len(not_refunded)} cancelled bookings are NOT fully refunded in QuickBooks")
                                    st.write("These bookings are cancelled in FareHarbour but still have non-zero amounts in QuickBooks:")
                                    display_cols = ['Booking_ID', 'FH_Total_Amount', 'QB_Amount', 'Total_Amount_Difference']
                                    available_cols = [col for col in display_cols if col in not_refunded.columns]
                                    st.dataframe(not_refunded[available_cols], use_container_width=True)
                                else:
                                    st.success("✅ All cancelled bookings are properly refunded (net $0) in QuickBooks")
                    
                    # Show summary statistics
                    col1, col2, col3 = st.columns(3)
                    
                    # Calculate summary metrics based on available difference columns
                    total_amount_diff = 0
                    avg_amount_diff = 0
                    max_amount_diff = 0
                    
                    if 'Total_Amount_Difference' in amount_diffs.columns:
                        total_amount_diff = amount_diffs['Total_Amount_Difference'].sum()
                        avg_amount_diff = amount_diffs['Total_Amount_Difference'].mean()
                        max_amount_diff = amount_diffs['Total_Amount_Difference'].abs().max()
                    
                    with col1:
                        st.metric("Total Amount Difference", f"${total_amount_diff:,.2f}")
                    with col2:
                        st.metric("Avg Amount Difference", f"${avg_amount_diff:,.2f}")
                    with col3:
                        st.metric("Max Amount Difference", f"${max_amount_diff:,.2f}")
                    
                    # Show breakdown by difference type
                    st.subheader("📊 Breakdown by Difference Type")
                    
                    diff_cols = [col for col in amount_diffs.columns if col.endswith('_Difference')]
                    if diff_cols:
                        breakdown_cols = st.columns(len(diff_cols))
                        for i, diff_col in enumerate(diff_cols):
                            with breakdown_cols[i]:
                                diff_type = diff_col.replace('_', ' ').title()
                                count = (abs(amount_diffs[diff_col]) > 0.01).sum()
                                st.metric(f"{diff_type} Issues", count)
                    
                    # Display the detailed comparison data with editable notes
                    st.subheader("📋 Detailed Comparison with Notes")
                    
                    # Create a more user-friendly display
                    display_df = amount_diffs_with_notes.copy()
                    
                    # Select columns to display with clear naming - Notes column first for visibility
                    display_cols = ['Booking_ID', 'Notes']
                    
                    # Add Created At Date for context
                    if 'Created At Date' in display_df.columns:
                        display_cols.append('Created At Date')
                    
                    # Add status columns first
                    status_cols = ['Is_Paid', 'Is_Cancelled']
                    for col in status_cols:
                        if col in display_df.columns:
                            display_cols.append(col)
                    
                    # Add FareHarbour columns
                    fh_cols = [col for col in display_df.columns if col.startswith('FH_')]
                    display_cols.extend(fh_cols)
                    
                    # Add QuickBooks columns  
                    qb_cols = [col for col in display_df.columns if col.startswith('QB_')]
                    display_cols.extend(qb_cols)
                    
                    # Add difference columns
                    diff_cols = [col for col in display_df.columns if col.endswith('_Difference')]
                    display_cols.extend(diff_cols)
                    
                    # Filter to only include columns that exist
                    display_cols = [col for col in display_cols if col in display_df.columns]
                    
                    # Use data editor for interactive editing of notes
                    st.info("💡 You can edit notes directly in the table below. Click 'Save Notes' to persist your changes.")
                    
                    edited_df = st.data_editor(
                        display_df[display_cols],
                        column_config={
                            "Notes": st.column_config.TextColumn(
                                "Notes",
                                help="Add your notes for this booking discrepancy",
                                max_chars=500,
                                width="medium"
                            ),
                            "Booking_ID": st.column_config.TextColumn(
                                "Booking ID",
                                help="FareHarbour Booking ID",
                                disabled=True,
                                width="small"
                            )
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="amount_differences_editor"
                    )
                    
                    # Save notes button
                    col_save, col_export = st.columns(2)
                    
                    with col_save:
                        if st.button("💾 Save Notes", type="primary"):
                            # Extract notes from edited dataframe
                            notes_to_save = {}
                            for _, row in edited_df.iterrows():
                                booking_id = str(row['Booking_ID'])
                                note = row['Notes'] if pd.notna(row['Notes']) else ''
                                if note.strip():  # Only save non-empty notes
                                    notes_to_save[booking_id] = note.strip()
                            
                            # Save to CSV
                            if save_notes_to_csv(notes_to_save):
                                st.success(f"✅ Successfully saved notes for {len(notes_to_save)} bookings!")
                                st.balloons()
                                # Refresh the display to show updated notes
                                st.rerun()
                            else:
                                st.error("❌ Failed to save notes. Please try again.")
                    
                    with col_export:
                        if st.button("📥 Export Amount Differences"):
                            # Include notes in the export
                            excel_data = export_to_excel({
                                "Amount_Differences": edited_df,
                                "Amount_Differences_All_Columns": amount_diffs_with_notes
                            })
                            st.download_button(
                                label="Download Excel",
                                data=excel_data,
                                file_name=f"amount_differences_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    
                    # Show notes statistics
                    notes_count = edited_df['Notes'].notna().sum() if 'Notes' in edited_df.columns else 0
                    non_empty_notes = edited_df['Notes'].fillna('').str.strip().ne('').sum() if 'Notes' in edited_df.columns else 0
                    
                    st.markdown(f"""
                    **Notes Statistics:** {non_empty_notes} bookings have notes out of {len(edited_df)} total discrepancies
                    """)
                    
                    # Color coding explanation
                    st.markdown("""
                    **Column Legend:**
                    - `Notes` = Your editable notes for each booking discrepancy
                    - `FH_*` = FareHarbour data
                    - `QB_*` = QuickBooks data  
                    - `*_Difference` = FareHarbour value minus QuickBooks value
                    """)
                    
                    # Show existing notes file info
                    if os.path.exists("reconciliation_notes.csv"):
                        file_stat = os.stat("reconciliation_notes.csv")
                        file_size = file_stat.st_size
                        file_modified = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        
                        with st.expander("📁 Notes File Information"):
                            st.write(f"**File:** reconciliation_notes.csv")
                            st.write(f"**Size:** {file_size} bytes")
                            st.write(f"**Last Modified:** {file_modified}")
                            st.write(f"**Total Saved Notes:** {len(existing_notes)}")
                            
                            if st.button("🗑️ Clear All Notes"):
                                if os.path.exists("reconciliation_notes.csv"):
                                    os.remove("reconciliation_notes.csv")
                                    st.success("All notes cleared!")
                                    st.rerun()
                
                else:
                    st.success("✅ No amount discrepancies found!")
            
            # Add payment/refund comparison tab if payments data is available
            if fh_payments_df is not None:
                with tab4:
                    st.subheader("💳 Payment & Refund Comparison")
                    st.info("""
                    **Comparison Logic:**
                    - **Total Activity**: Sum of all FareHarbour payments + refunds vs QuickBooks payments + refunds
                    - **Payment Amounts**: FareHarbour gross payment amounts vs QuickBooks positive amounts
                    - **Refund Amounts**: FareHarbour gross refund amounts vs QuickBooks negative amounts
                    - **Missing Transaction Analysis**: Identifies specific missing payments or refunds
                    - **Transaction Counts**: Number of payment/refund transactions per booking
                    
                    *Note: We compare FareHarbour GROSS amounts to QuickBooks amounts since QB records full transaction amounts before processing fees.*
                    """)
                    
                    payment_comparison = compare_payments_refunds(fh_payments_df, qb_df)
                    
                    if not payment_comparison.empty:
                        st.warning(f"Found {len(payment_comparison)} bookings with payment/refund discrepancies")
                        
                        # Show summary metrics
                        col1, col2, col3, col4 = st.columns(4)
                        
                        # Calculate summary metrics
                        if 'Total_Activity_Difference' in payment_comparison.columns:
                            total_activity_diff = payment_comparison['Total_Activity_Difference'].sum()
                            max_activity_diff = payment_comparison['Total_Activity_Difference'].abs().max()
                        else:
                            total_activity_diff = 0
                            max_activity_diff = 0
                        
                        with col1:
                            st.metric("Total Activity Difference", f"${total_activity_diff:,.2f}")
                        with col2:
                            st.metric("Max Activity Difference", f"${max_activity_diff:,.2f}")
                        with col3:
                            if 'Has_Activity_Difference' in payment_comparison.columns:
                                activity_issues = payment_comparison['Has_Activity_Difference'].sum()
                                st.metric("Activity Issues", activity_issues)
                        with col4:
                            if 'Missing_Transaction_Type' in payment_comparison.columns:
                                missing_issues = (payment_comparison['Missing_Transaction_Type'] != 'None').sum()
                                st.metric("Missing Transactions", missing_issues)
                        
                        # Show breakdown by issue type
                        st.subheader("📊 Issue Breakdown")
                        issue_types = []
                        
                        if 'Has_Activity_Difference' in payment_comparison.columns:
                            activity_issues = payment_comparison['Has_Activity_Difference'].sum()
                            issue_types.append(f"Total Activity Differences: {activity_issues}")
                        
                        if 'Has_Payment_Difference' in payment_comparison.columns:
                            payment_issues = payment_comparison['Has_Payment_Difference'].sum()
                            issue_types.append(f"Payment Amount Differences: {payment_issues}")
                        
                        if 'Has_Refund_Difference' in payment_comparison.columns:
                            refund_issues = payment_comparison['Has_Refund_Difference'].sum()
                            issue_types.append(f"Refund Amount Differences: {refund_issues}")
                        
                        if 'Has_Tax_Difference' in payment_comparison.columns:
                            tax_issues = payment_comparison['Has_Tax_Difference'].sum()
                            issue_types.append(f"Tax Differences: {tax_issues}")
                        
                        if 'Has_Transaction_Count_Difference' in payment_comparison.columns:
                            count_issues = payment_comparison['Has_Transaction_Count_Difference'].sum()
                            issue_types.append(f"Transaction Count Differences: {count_issues}")
                        
                        # Show missing transaction breakdown
                        if 'Missing_Transaction_Type' in payment_comparison.columns:
                            st.subheader("🚨 Missing Transaction Analysis")
                            missing_breakdown = payment_comparison['Missing_Transaction_Type'].value_counts()
                            for transaction_type, count in missing_breakdown.items():
                                if transaction_type != 'None':
                                    st.write(f"• {transaction_type}: {count} bookings")
                        
                        for issue_type in issue_types:
                            st.write(f"• {issue_type}")
                        
                        # Display detailed comparison data with notes
                        st.subheader("📋 Detailed Payment/Refund Comparison with Notes")
                        
                        # Load existing notes for payment/refund comparison
                        payment_notes_file = "payment_refund_notes.csv"
                        existing_payment_notes = load_notes_from_csv(payment_notes_file)
                        
                        # Merge notes with payment comparison data
                        payment_comparison_with_notes = merge_notes_with_data(payment_comparison, existing_payment_notes, 'Booking_ID')
                        
                        # Create notes editor
                        edited_payment_df, display_cols = create_notes_editor(
                            payment_comparison_with_notes, 
                            "Payment/Refund Comparison", 
                            "payment"
                        )
                        
                        # Save and export buttons
                        col_save, col_export = st.columns(2)
                        
                        with col_save:
                            if st.button("💾 Save Payment/Refund Notes", type="primary", key="save_payment_notes"):
                                if save_table_notes(edited_payment_df, payment_notes_file, "Payment/Refund Comparison"):
                                    st.rerun()
                        
                        with col_export:
                            if st.button("📥 Export Payment/Refund Comparison", key="export_payment"):
                                excel_data = export_to_excel({
                                    "Payment_Refund_Comparison": edited_payment_df,
                                    "Payment_Refund_All_Columns": payment_comparison_with_notes,
                                    "FH_Payments_Summary": fh_payments_df.groupby(['Booking ID Clean', 'Payment or Refund']).agg({
                                        'Net': 'sum',
                                        'Gross': 'sum',
                                        'Processing Fee': 'sum'
                                    }).reset_index()
                                })
                                st.download_button(
                                    label="Download Excel",
                                    data=excel_data,
                                    file_name=f"payment_refund_comparison_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                        
                        # Show notes statistics
                        non_empty_notes = edited_payment_df['Notes'].fillna('').str.strip().ne('').sum() if 'Notes' in edited_payment_df.columns else 0
                        st.markdown(f"""
                        **Notes Statistics:** {non_empty_notes} payment/refund issues have notes out of {len(edited_payment_df)} total
                        """)
                        
                        # Show notes file info
                        show_notes_file_info(payment_notes_file, "Payment/Refund Comparison", existing_payment_notes)
                        
                        # Color coding explanation
                        st.markdown("""
                        **Column Legend:**
                        - `Missing_Transaction_Type` = Analysis of what's missing in QuickBooks
                        - `FH_Total_Activity` = Sum of all FareHarbour payments + refunds (gross)
                        - `QB_Total_Activity` = Sum of all QuickBooks payments + refunds
                        - `FH_*` = FareHarbour payments data (gross amounts used for comparison)
                        - `QB_*` = QuickBooks data
                        - `*_Difference` = FareHarbour gross amount minus QuickBooks amount
                        - `*_Count` = Number of transactions
                        """)
                    
                    else:
                        st.success("✅ No payment/refund discrepancies found!")
                        
                        # Show summary even when no discrepancies
                        if fh_payments_df is not None:
                            st.subheader("📊 Payment Summary")
                            
                            # Overall summary
                            total_payments = fh_payments_df[fh_payments_df['Is_Payment']]['Net'].sum() if 'Is_Payment' in fh_payments_df.columns else 0
                            total_refunds = fh_payments_df[fh_payments_df['Is_Refund']]['Net'].sum() if 'Is_Refund' in fh_payments_df.columns else 0
                            net_amount = total_payments - total_refunds
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Total Payments", f"${total_payments:,.2f}")
                            with col2:
                                st.metric("Total Refunds", f"${total_refunds:,.2f}")
                            with col3:
                                st.metric("Net Amount", f"${net_amount:,.2f}")
            
            # Summary Report Tab (now tab5 if payments data exists, otherwise tab4)
            summary_tab = tab5 if fh_payments_df is not None else tab4
            
            with summary_tab:
                st.subheader("📈 Reconciliation Summary Report")
                
                # Generate summary statistics
                missing_count = len(find_missing_bookings(fh_df, qb_df))
                cancelled_open_count = len(find_cancelled_vs_open(fh_df, qb_df))
                amount_diff_count = len(compare_amounts(fh_df, qb_df))
                
                # Add payment comparison count if available
                payment_diff_count = 0
                if fh_payments_df is not None:
                    payment_diff_count = len(compare_payments_refunds(fh_payments_df, qb_df))
                
                # Summary metrics - adjust columns based on whether payments data is available
                if fh_payments_df is not None:
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col5:
                        st.metric("Payment/Refund Issues", payment_diff_count)
                else:
                    col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Missing Bookings", missing_count)
                with col2:
                    st.metric("Cancelled/Open Issues", cancelled_open_count)
                with col3:
                    st.metric("Amount Discrepancies", amount_diff_count)
                with col4:
                    total_issues = missing_count + cancelled_open_count + amount_diff_count + payment_diff_count
                    st.metric("Total Issues", total_issues)
                
                # Generate comprehensive report
                if st.button("📊 Generate Full Report"):
                    # Load all notes files and merge with data
                    missing_notes = load_notes_from_csv("missing_bookings_notes.csv")
                    cancelled_notes = load_notes_from_csv("cancelled_vs_open_notes.csv")
                    amount_notes = load_notes_from_csv("reconciliation_notes.csv")
                    
                    # Get base data with notes
                    missing_with_notes = merge_notes_with_data(find_missing_bookings(fh_df, qb_df), missing_notes, 'Booking ID Clean')
                    cancelled_with_notes = merge_notes_with_data(find_cancelled_vs_open(fh_df, qb_df), cancelled_notes, 'Booking ID Clean')
                    amount_with_notes = merge_notes_with_data(compare_amounts(fh_df, qb_df), amount_notes)
                    
                    all_data = {
                        "Missing_Bookings": missing_with_notes,
                        "Cancelled_vs_Open": cancelled_with_notes,
                        "Amount_Differences": amount_with_notes,
                        "FH_Summary": fh_df.groupby(['Paid Status', 'Cancelled?']).size().reset_index(name='Count'),
                        "QB_Summary": qb_df.groupby(qb_df['Open_Balance'] > 0).size().reset_index(name='Count')
                    }
                    
                    # Add payment comparison data if available
                    if fh_payments_df is not None:
                        payment_notes = load_notes_from_csv("payment_refund_notes.csv")
                        payment_comparison = compare_payments_refunds(fh_payments_df, qb_df)
                        payment_with_notes = merge_notes_with_data(payment_comparison, payment_notes, 'Booking_ID')
                        all_data["Payment_Refund_Comparison"] = payment_with_notes
                        
                        # Add FareHarbour payments summary
                        if not fh_payments_df.empty:
                            payments_summary = fh_payments_df.groupby(['Booking ID Clean', 'Payment or Refund']).agg({
                                'Net': 'sum',
                                'Gross': 'sum', 
                                'Processing Fee': 'sum',
                                'Tax Paid': 'sum'
                            }).reset_index()
                            all_data["FH_Payments_Summary"] = payments_summary
                    
                    # Add notes summaries to the report
                    all_notes_summary = []
                    
                    for notes_file, table_name in [
                        ("missing_bookings_notes.csv", "Missing Bookings"),
                        ("cancelled_vs_open_notes.csv", "Cancelled vs Open"),
                        ("reconciliation_notes.csv", "Amount Differences"),
                        ("payment_refund_notes.csv", "Payment/Refund Comparison")
                    ]:
                        if os.path.exists(notes_file):
                            notes_df = pd.read_csv(notes_file)
                            if not notes_df.empty:
                                notes_df['Table_Type'] = table_name
                                all_notes_summary.append(notes_df)
                    
                    if all_notes_summary:
                        combined_notes = pd.concat(all_notes_summary, ignore_index=True)
                        all_data["All_Notes_Summary"] = combined_notes
                    
                    excel_data = export_to_excel(all_data)
                    st.download_button(
                        label="📥 Download Complete Reconciliation Report",
                        data=excel_data,
                        file_name=f"reconciliation_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                    st.success("Report generated successfully!")
    
    else:
        # Instructions when no files uploaded
        st.info("👆 Please upload both FareHarbour CSV and QuickBooks Excel files to begin reconciliation.")
        
        with st.expander("📋 File Format Requirements"):
            st.markdown("""
            **FareHarbour Bookings CSV Requirements:**
            - Export the bookings report from FareHarbour
            - Should contain columns: Booking ID, Contact, Total Paid, Paid Status, Cancelled?, etc.
            - Format: CSV file
            
            **FareHarbour Payments CSV Requirements (Optional):**
            - Export the payments/refunds report from FareHarbour
            - Should contain columns: Payment or Refund, Booking ID, Gross, Net, Processing Fee, etc.
            - First row should contain "Sales" and "Bookings" headers (will be skipped)
            - Format: CSV file
            
            **QuickBooks Excel Requirements:**
            - Export the transaction list by date
            - Should contain FareHarbour booking references
            - Format: Excel (.xlsx or .xls)
            """)
        
        with st.expander("🎯 What This Tool Does"):
            st.markdown("""
            This reconciliation tool helps you identify:
            
            1. **Missing Bookings**: Bookings that exist in FareHarbour but not in QuickBooks
            2. **Cancelled vs Open**: Bookings cancelled in FareHarbour but still showing as open invoices in QuickBooks
            3. **Amount Differences**: Discrepancies in amounts between the two systems
            4. **Payment/Refund Comparison**: Compare individual payments and refunds between FareHarbour and QuickBooks (requires optional payments CSV)
            5. **Summary Reports**: Comprehensive analysis with exportable Excel reports
            
            **New Payment/Refund Analysis Features:**
            - Compare net payment amounts per booking
            - Identify missing or mismatched refunds
            - Analyze payment processing fees
            - Track transaction counts per booking
            - Export detailed payment reconciliation reports
            """)

if __name__ == "__main__":
    main() 