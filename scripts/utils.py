# Utility functions for the reconciliation app
import pandas as pd
import streamlit as st
from datetime import datetime
from io import BytesIO
import os
from scripts.config import NOTES_FILES
from scripts.database import execute_query

def export_to_excel(dataframes_dict):
    """Export multiple dataframes to Excel with different sheets"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in dataframes_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    processed_data = output.getvalue()
    return processed_data

def void_invoices_in_quickbooks(cancelled_data, webhook_url=None):
    """
    Void invoices in QuickBooks using webhook for each document number

    Args:
        cancelled_data: DataFrame with cancelled bookings that have open QB invoices
        webhook_url: The n8n webhook URL to call for voiding invoices (uses env var if None)

    Returns:
        dict: Results of the voiding process
    """
    from scripts.config import ENABLE_VOID_FEATURE, WEBHOOK_URL, API_KEY
    import requests
    import time

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
