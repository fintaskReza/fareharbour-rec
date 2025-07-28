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

# Security configuration
ENABLE_VOID_FEATURE = os.getenv("ENABLE_VOID_FEATURE", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://n8n.fintask.ie/webhook/void_inv")
API_KEY = os.getenv("API_KEY", "")

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

def main():
    st.title("🔍 FareHarbour - QuickBooks Reconciliation Tool")
    st.markdown("Upload your FareHarbour CSV and QuickBooks Excel files to compare bookings and identify discrepancies.")
    
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