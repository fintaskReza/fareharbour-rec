# Data loading functions for CSV and Excel files
import pandas as pd
import numpy as np
from datetime import datetime
import re
import streamlit as st

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

        # Force skip first row if first column is "Bookings" (even if condition didn't work)
        if df.columns[0] == "Bookings":
            # st.write("DEBUG: Detected 'Bookings' header, re-reading with skiprows=1")
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, skiprows=1)
            df.columns = df.columns.str.strip()

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
                # Remove currency symbols, commas, and handle negative values in format like "-$0.81"
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
