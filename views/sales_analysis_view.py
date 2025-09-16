# Sales Report Analysis View
import streamlit as st
import pandas as pd
from datetime import datetime
from scripts.data_loaders import load_sales_csv_data
from scripts.database import execute_query
from scripts.journal_exports import (
    create_enhanced_quickbooks_journal_v2,
    create_v2_detailed_records,
    create_tour_pivot_table,
    get_quickbooks_mappings
)

def generate_v2_export(df, pivot_data, include_processing_fees=False):
    """Generate V2 export excluding affiliate bookings where payment already received"""
    st.markdown("---")
    st.subheader("🎯 V2 Export Results (Filtered Bookings)")

    # Filter out bookings where affiliate payment already received
    v2_raw_df = df.copy()
    v2_raw_df['Receivable from Affiliate'] = pd.to_numeric(v2_raw_df.get('Receivable from Affiliate', 0), errors='coerce').fillna(0)
    v2_raw_df['Received from Affiliate'] = pd.to_numeric(v2_raw_df.get('Received from Affiliate', 0), errors='coerce').fillna(0)

    # Remove bookings where affiliate payment already received
    v2_filtered_df = v2_raw_df[
        ~((v2_raw_df['Receivable from Affiliate'] > 0) | (v2_raw_df['Received from Affiliate'] > 0))
    ].copy()

    if not v2_filtered_df.empty:
        # Recalculate pivot table for V2
        v2_pivot_df = create_tour_pivot_table(v2_filtered_df)

        if not v2_pivot_df.empty:

            # Generate V2 journal and detailed records
            v2_journal_df, total_vat_payments, total_vat_refunds, v2_payment_type_totals, v2_processing_fees_totals, v2_net_payment_totals = create_enhanced_quickbooks_journal_v2(v2_pivot_df, v2_filtered_df, include_processing_fees)

            if not v2_journal_df.empty:
                # Generate detailed records
                v2_detailed_records = create_v2_detailed_records(v2_filtered_df)

                # Store CSV data in session state
                st.session_state.v2_pivot_csv = v2_pivot_df.to_csv(index=False)
                st.session_state.v2_filtered_csv = v2_filtered_df.to_csv(index=False)
                st.session_state.v2_journal_csv = v2_journal_df.to_csv(index=False)
                st.session_state.v2_detailed_csv = v2_detailed_records.to_csv(index=False)
                st.session_state.v2_payment_type_totals = v2_payment_type_totals
                st.session_state.v2_processing_fees_totals = v2_processing_fees_totals
                st.session_state.v2_net_payment_totals = v2_net_payment_totals

                # Create tabs for exports and previews
                export_tab, downloads_tab = st.tabs(["📚 Journal Export", "📥 Additional Downloads"])
                
                with export_tab:
                    # Main journal export - full width
                    st.markdown("### 📚 V2 QuickBooks Journal Export")
                    
                    # Primary journal download button - full width
                    st.download_button(
                        label="📚 Download V2 Journal + Details",
                        data=st.session_state.v2_journal_csv,
                        file_name=f"quickbooks_journal_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime='text/csv',
                        help="Download V2 QuickBooks journal entries with detailed records",
                        use_container_width=True
                    )
                    
                    # Journal preview - full width with column summations
                    st.markdown("#### 🔍 Journal Preview")
                    
                    # Calculate column summations
                    total_credits = pd.to_numeric(v2_journal_df['Credit'].replace('', '0'), errors='coerce').sum()
                    total_debits = pd.to_numeric(v2_journal_df['Debit'].replace('', '0'), errors='coerce').sum()
                    
                    # Display the journal with full width
                    st.dataframe(v2_journal_df, use_container_width=True, height=400)
                    
                    # Show column summations at bottom
                    sum_col1, sum_col2, sum_col3 = st.columns(3)
                    with sum_col1:
                        st.metric("Total Credits", f"${total_credits:,.2f}")
                    with sum_col2:
                        st.metric("Total Debits", f"${total_debits:,.2f}")
                    with sum_col3:
                        balance = total_credits - total_debits
                        st.metric("Balance", f"${balance:,.2f}", delta=f"{'Balanced' if abs(balance) < 0.01 else 'Unbalanced'}")

                with downloads_tab:
                    st.markdown("### 📥 Additional V2 Downloads")
                    
                    # Other downloads in columns
                    dl_col1, dl_col2, dl_col3 = st.columns(3)
                    
                    with dl_col1:
                        st.download_button(
                            label="📊 Download V2 Pivot Table",
                            data=st.session_state.v2_pivot_csv,
                            file_name=f"sales_pivot_table_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime='text/csv',
                            help="Download V2 pivot table (excludes affiliate payments received)",
                            use_container_width=True
                        )

                    with dl_col2:
                        st.download_button(
                            label="📋 Download V2 Filtered Data",
                            data=st.session_state.v2_filtered_csv,
                            file_name=f"sales_filtered_data_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime='text/csv',
                            help="Download V2 filtered raw data",
                            use_container_width=True
                        )

                    with dl_col3:
                        st.download_button(
                            label="📑 Download V2 Detailed Records",
                            data=st.session_state.v2_detailed_csv,
                            file_name=f"v2_detailed_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime='text/csv',
                            help="Download detailed records with fee breakdown and net amounts",
                            use_container_width=True
                        )
                    
                    # Preview for detailed records
                    with st.expander("📋 Preview V2 Detailed Records"):
                        preview_df = v2_detailed_records.head(10).copy()
                        if len(v2_detailed_records) > 10:
                            st.info(f"Showing first 10 of {len(v2_detailed_records)} records")
                        st.dataframe(preview_df, use_container_width=True)


            else:
                st.warning("⚠️ No V2 journal entries generated.")
        else:
            st.warning("⚠️ No V2 pivot table data available.")
    else:
        st.warning("⚠️ All bookings were excluded by V2 filter (all had affiliate payments already received).")


def sales_report_analysis():
    """Sales Report Analysis Page with CSV Upload and Pivot Tables"""
    st.title("📊 Sales Report Analysis")

    # Compact CSS
    st.markdown("""
    <style>
    .stDataFrame {border: 1px solid #e9ecef; border-radius: 6px;}
    </style>
    """, unsafe_allow_html=True)

    # Initialize session state for downloads
    if 'v2_pivot_csv' not in st.session_state:
        st.session_state.v2_pivot_csv = None
    if 'v2_filtered_csv' not in st.session_state:
        st.session_state.v2_filtered_csv = None
    if 'v2_journal_csv' not in st.session_state:
        st.session_state.v2_journal_csv = None
    if 'v2_detailed_csv' not in st.session_state:
        st.session_state.v2_detailed_csv = None

    # File upload section
    st.sidebar.header("📁 Sales Report Upload")

    # Default CSV file for local development
    default_csv_path = "/Users/reza/Documents/GitHub/Fareharbour/Custom-sales-report--2025-07-25--2025-08-23.csv"
    default_file_loaded = False

    # Check if default file exists and load it automatically
    import os
    import io
    if os.path.exists(default_csv_path):
        try:
            with open(default_csv_path, 'rb') as f:
                default_csv_content = f.read()

            # Convert bytes to file-like object for pandas
            csv_file_like = io.BytesIO(default_csv_content)

            # Load the default CSV
            with st.spinner("Loading default sales report for development..."):
                df = load_sales_csv_data(csv_file_like)
                default_file_loaded = True

            st.sidebar.success("✅ Default CSV loaded for development")
            st.sidebar.info("💡 Upload a different file above to override")

        except Exception as e:
            st.sidebar.warning(f"⚠️ Could not load default CSV: {str(e)}")
            df = None
    else:
        df = None

    # File uploader for manual upload (overrides default)
    sales_csv_file = st.sidebar.file_uploader(
        "Upload Sales Report CSV (overrides default)",
        type=['csv'],
        help="Upload the FareHarbour sales report CSV file"
    )

    # Payout CSV upload in sidebar
    st.sidebar.markdown("---")
    st.sidebar.header("💰 Payout Report Upload")
    st.sidebar.markdown("Upload payout CSV for journal comparison")
    
    payout_csv_file = st.sidebar.file_uploader(
        "Upload Payout CSV Report",
        type=['csv'],
        help="Upload the payout CSV file to compare with journal payment totals",
        key="payout_comparison_upload_sidebar"
    )
    
    # Store payout data in session state
    if payout_csv_file is not None:
        try:
            payout_df = pd.read_csv(payout_csv_file)
            st.session_state.payout_df = payout_df
            st.sidebar.success(f"✅ Payout CSV loaded ({len(payout_df)} records)")
        except Exception as e:
            st.sidebar.error(f"❌ Error loading payout CSV: {str(e)}")
            st.session_state.payout_df = None
    elif 'payout_df' not in st.session_state:
        st.session_state.payout_df = None

    # Use uploaded file if provided, otherwise use default
    if sales_csv_file is not None:
        try:
            with st.spinner("Loading and processing uploaded sales report..."):
                df = load_sales_csv_data(sales_csv_file)
                default_file_loaded = False
        except Exception as e:
            st.error(f"❌ Error loading uploaded file: {str(e)}")
            return

    # Process the data if we have it
    if df is not None and not df.empty:
        try:
            # Create tabs for different analyses
            tab1, tab2 = st.tabs(["📊 Pivot Analysis", "📈 Payment & Affiliate Breakdown"])

            with tab1:
                # Create pivot table and filters
                create_sales_pivot_analysis(df)

            with tab2:
                # Create detailed breakdown analysis
                create_payment_affiliate_breakdown(df)

            # Add payout comparison section as a separate tab/section
            st.markdown("---")
            st.subheader("💰 Payout vs Journal Comparison")
            create_payout_comparison_section(df)

        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
            st.info("💡 Make sure the CSV has the correct format with headers starting on the second row.")
    else:
        # Instructions for file format
        if not default_file_loaded:
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
        else:
            st.info("📊 Default CSV loaded successfully! You can now analyze the data or upload a different file to override.")

def create_sales_pivot_analysis(df):
    """Create pivot table analysis with filtering"""
    # Use the full dataframe without filtering
    filtered_df = df.copy()

    # Create pivot table
    if not filtered_df.empty:
        pivot_data = create_tour_pivot_table(filtered_df)

        if not pivot_data.empty:

            # Export functionality - Automatic V2 Generation
            st.markdown("### 🎯 Export Options")
            include_processing_fees = st.checkbox(
                "💳 Include Processing Fee Expenses",
                value=True,
                help="Include platform processing fees (Stripe, PayPal, etc.) as separate expense lines in journal entries"
            )

            if include_processing_fees:
                pass  # Processing fees included

            # V2 Export (automatic generation when data is available)
            # Automatically generate V2 export when data is available
            with st.spinner("Generating V2 journal export..."):
                generate_v2_export(df, pivot_data, include_processing_fees)
        else:
            st.warning("⚠️ No data available for pivot table creation.")
    else:
        st.warning("⚠️ No data matches the selected filters.")

# Removed duplicate create_tour_pivot_table function - using import from scripts.journal_exports

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

# Removed duplicate function - using import from scripts.journal_exports  
# Removed duplicate get_quickbooks_mappings function - using import from scripts.journal_exports

def get_fallback_mappings():
    """Fallback mappings when database is unavailable"""
    return {
        'tour_revenue': {},
        'fee_revenue': {},
        'payment_type': {
            'Credit Card': {'account': 'Credit Card Clearing', 'account_type': 'asset', 'account_id': ''},
            'Cash': {'account': 'Cash - Operating', 'account_type': 'asset', 'account_id': ''},
            'PayPal': {'account': 'PayPal Clearing', 'account_type': 'asset', 'account_id': ''},
            'Check': {'account': 'Undeposited Funds', 'account_type': 'asset', 'account_id': ''},
            'Bank Transfer': {'account': 'Bank Transfer Clearing', 'account_type': 'asset', 'account_id': ''},
        }
    }

# Removed duplicate function - using import from scripts.journal_exports

# Removed duplicate V2 function - using import from scripts.journal_exports

def calculate_payment_breakdown(transactions):
    """Calculate payment amounts by payment type for a tour"""
    try:
        payment_breakdown = {}

        if 'Payment Type' in transactions.columns:
            # Group by payment type and sum payment amounts
            payment_summary = transactions.groupby('Payment Type').agg({
                'Total Paid': 'sum'
            }).reset_index()

            for _, row in payment_summary.iterrows():
                payment_type = row['Payment Type']
                amount = pd.to_numeric(row['Total Paid'], errors='coerce')
                if amount > 0:
                    payment_breakdown[payment_type] = amount
        else:
            # Fallback if Payment Type column doesn't exist
            total_paid = transactions['Total Paid'].sum() if 'Total Paid' in transactions.columns else 0
            if total_paid > 0:
                payment_breakdown['Unknown'] = total_paid

        return payment_breakdown

    except Exception as e:
        # Fallback to single payment type
        total_paid = transactions['Total Paid'].sum() if 'Total Paid' in transactions.columns else 0
        return {'Unknown': total_paid} if total_paid > 0 else {}

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

def calculate_proportional_fees_streamlit(subtotal_paid, subtotal_total, total_fees_for_booking):
    """
    Calculate proportional fees based on partial payment - same logic as test script
    Formula: (Subtotal Paid / Subtotal Total) * Total Fees
    
    Special cases:
    - If subtotal_total is 0, return 0
    - If payment >= subtotal (overpayment), cap proportion at 1.0 (100% of fees)
    """
    if subtotal_total == 0:
        return 0
    
    proportion = abs(subtotal_paid) / subtotal_total  # Use abs for refunds
    
    # Cap proportion at 1.0 for overpayment scenarios
    proportion = min(proportion, 1.0)
    
    return proportion * total_fees_for_booking


def display_payment_refund_pivot_table(df):
    """Display pivot table with Payment/Refund breakdown by tour matching the requested layout"""
    try:
        # Get fee mappings from database for calculations
        fee_mappings = execute_query("""
            SELECT t.name as tour_name, f.name as fee_name, f.per_person_amount
            FROM tour_fees tf
            JOIN tours t ON tf.tour_id = t.id
            JOIN fees f ON tf.fee_id = f.id
            ORDER BY t.name, f.name
        """)
        
        fee_mappings_df = pd.DataFrame(fee_mappings, columns=['tour_name', 'fee_name', 'per_person_amount']) if fee_mappings else pd.DataFrame()
        if not fee_mappings_df.empty:
            fee_mappings_df['per_person_amount'] = pd.to_numeric(fee_mappings_df['per_person_amount'], errors='coerce').fillna(0)

        # Create the pivot structure
        pivot_data = []
        
        # Get unique tours
        tours = df['Item'].unique()
        
        # Process payments - using proportional fees like test script
        payments_df = df[df['Payment or Refund'] == 'Payment']
        for tour in tours:
            tour_payments = payments_df[payments_df['Item'] == tour]
            if not tour_payments.empty:
                total_ex_fee_subtotal = 0
                total_proportional_fees = 0
                
                # Process each payment transaction separately for proportional fees
                for _, row in tour_payments.iterrows():
                    subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
                    subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
                    guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
                    
                    # Calculate total fees for this booking (full booking)
                    total_fees_for_booking = 0
                    if not fee_mappings_df.empty:
                        tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour]
                        for _, fee_row in tour_fees.iterrows():
                            total_fees_for_booking += fee_row['per_person_amount'] * guests
                    
                    # Calculate proportional fees based on payment amount
                    proportional_fees = calculate_proportional_fees_streamlit(subtotal_paid, subtotal_total, float(total_fees_for_booking))
                    
                    # Ex-fee subtotal = Subtotal Paid - Proportional Fees
                    ex_fee_subtotal = subtotal_paid - proportional_fees
                    
                    total_ex_fee_subtotal += ex_fee_subtotal
                    total_proportional_fees += proportional_fees
                
                pivot_data.append({
                    'Payment or Refund': 'Payment',
                    'Item': tour,
                    'SUM of Ex fee sub paid': total_ex_fee_subtotal,
                    'SUM of Fees': total_proportional_fees
                })
        
        # Process refunds - using proportional fees like test script
        refunds_df = df[df['Payment or Refund'] == 'Refund']
        for tour in tours:
            tour_refunds = refunds_df[refunds_df['Item'] == tour]
            if not tour_refunds.empty:
                total_ex_fee_subtotal = 0
                total_proportional_fees = 0
                
                # Process each refund transaction separately for proportional fees
                for _, row in tour_refunds.iterrows():
                    subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
                    subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
                    guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
                    
                    # Calculate total fees for this booking (full booking)
                    total_fees_for_booking = 0
                    if not fee_mappings_df.empty:
                        tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour]
                        for _, fee_row in tour_fees.iterrows():
                            total_fees_for_booking += fee_row['per_person_amount'] * guests
                    
                    # Calculate proportional fees based on refund amount
                    proportional_fees = calculate_proportional_fees_streamlit(subtotal_paid, subtotal_total, float(total_fees_for_booking))
                    
                    # Ex-fee subtotal = Subtotal Paid + Proportional Fees (since subtotal_paid is already negative)
                    ex_fee_subtotal = subtotal_paid + proportional_fees
                    
                    total_ex_fee_subtotal += ex_fee_subtotal
                    total_proportional_fees += proportional_fees
                
                pivot_data.append({
                    'Payment or Refund': 'Refund',
                    'Item': tour,
                    'SUM of Ex fee sub paid': total_ex_fee_subtotal,
                    'SUM of Fees': -total_proportional_fees  # Negative for refunds
                })
        
        # Convert to DataFrame
        pivot_df = pd.DataFrame(pivot_data)
        
        if pivot_df.empty:
            st.warning("No data available for pivot table")
            return
            
        # Create totals
        payment_totals = pivot_df[pivot_df['Payment or Refund'] == 'Payment'].agg({
            'SUM of Ex fee sub paid': 'sum',
            'SUM of Fees': 'sum'
        })
        
        refund_totals = pivot_df[pivot_df['Payment or Refund'] == 'Refund'].agg({
            'SUM of Ex fee sub paid': 'sum', 
            'SUM of Fees': 'sum'
        })
        
        # Add total rows
        pivot_df = pd.concat([
            pivot_df,
            pd.DataFrame([{
                'Payment or Refund': 'Payment Total',
                'Item': '',
                'SUM of Ex fee sub paid': payment_totals['SUM of Ex fee sub paid'],
                'SUM of Fees': payment_totals['SUM of Fees']
            }]),
            pd.DataFrame([{
                'Payment or Refund': 'Refund Total', 
                'Item': '',
                'SUM of Ex fee sub paid': refund_totals['SUM of Ex fee sub paid'],
                'SUM of Fees': refund_totals['SUM of Fees']
            }]),
            pd.DataFrame([{
                'Payment or Refund': 'Grand Total',
                'Item': '',
                'SUM of Ex fee sub paid': payment_totals['SUM of Ex fee sub paid'] + refund_totals['SUM of Ex fee sub paid'],
                'SUM of Fees': payment_totals['SUM of Fees'] + refund_totals['SUM of Fees']
            }])
        ], ignore_index=True)
        
        # Format for display
        display_df = pivot_df.copy()
        
        # Format currency columns
        for col in ['SUM of Ex fee sub paid', 'SUM of Fees']:
            display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "0")
        
        # Display the table
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Payment or Refund": st.column_config.TextColumn("Payment or Refund", width="small"),
                "Item": st.column_config.TextColumn("Item", width="medium"),
                "SUM of Ex fee sub paid": st.column_config.TextColumn("SUM of Ex fee sub paid", width="medium"),
                "SUM of Fees": st.column_config.TextColumn("SUM of Fees", width="medium"),
            }
        )

    except Exception as e:
        st.error(f"❌ Error displaying payment/refund pivot table: {str(e)}")
        # Fallback to original function
        display_pivot_table_fallback(df)

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
                           'Subtotal (Ex-Tax)', 'Total Fees per Person', 'Total Fee Revenue', 'Tour Revenue (Net of Fees)', 'Total Tax']

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

def display_pivot_table_fallback(df):
    """Fallback function for pivot table display"""
    pivot_data = create_tour_pivot_table(df)
    if not pivot_data.empty:
        display_pivot_table(pivot_data)

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


def create_payout_comparison_section(sales_df):
    """Create payout comparison section with CSV upload and period filtering"""
    try:
        # Check if journal data is available in session state
        journal_available = False
        journal_df = None
        journal_version = None
        payment_type_totals = {}
        processing_fees_totals = {}
        net_payment_totals = {}
        
        if 'v2_journal_csv' in st.session_state and st.session_state.v2_journal_csv:
            # Parse V2 journal from CSV string
            import io
            journal_df = pd.read_csv(io.StringIO(st.session_state.v2_journal_csv))
            payment_type_totals = st.session_state.get('v2_payment_type_totals', {})
            processing_fees_totals = st.session_state.get('v2_processing_fees_totals', {})
            net_payment_totals = st.session_state.get('v2_net_payment_totals', {})
            journal_available = True
            journal_version = "V2"
        
        # Check if payout data is available from sidebar
        payout_df = st.session_state.get('payout_df', None)
        
        if payout_df is not None and journal_available:
            try:
                # Validate required columns
                required_columns = ['period_end_date', 'net_payout_amount', 'gross_amount', 'processing_fee_amount']
                missing_columns = [col for col in required_columns if col not in payout_df.columns]
                
                if missing_columns:
                    st.error(f"❌ Missing required columns in payout CSV: {', '.join(missing_columns)}")
                    st.info("Expected columns: period_end_date, net_payout_amount, gross_amount, processing_fee_amount")
                    return
                
                # Convert date column
                payout_df['period_end_date'] = pd.to_datetime(payout_df['period_end_date'], errors='coerce')
                
                # Period selection
                
                # Use all payouts by default (no date filtering)
                filtered_payouts = payout_df.copy()

                if not filtered_payouts.empty:
                    # Show payout table with selection in collapsible container FIRST
                    with st.expander("💰 Available Payouts", expanded=True):  # Changed to expanded=True for immediate visibility
                        # Add selection checkboxes (all selected by default)
                        st.markdown("**Select payouts to include in comparison:**")

                        # Header row
                        col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2])
                        with col1:
                            st.markdown("**Include**")
                        with col2:
                            st.markdown("**Period End Date**")
                        with col3:
                            st.markdown("**Gross Amount**")
                        with col4:
                            st.markdown("**Processing Fees**")
                        with col5:
                            st.markdown("**Net Payout**")

                        selected_payouts = []
                        for idx, row in filtered_payouts.iterrows():
                            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2])

                            with col1:
                                selected = st.checkbox("", key=f"payout_{idx}", value=True)  # Default to True (selected)
                                if selected:
                                    selected_payouts.append(idx)

                            with col2:
                                st.write(row['period_end_date'].strftime('%Y-%m-%d'))
                            with col3:
                                st.write(f"${row['gross_amount']:,.2f}")
                            with col4:
                                st.write(f"${row['processing_fee_amount']:,.2f}")
                            with col5:
                                st.write(f"${row['net_payout_amount']:,.2f}")

                        # Calculate totals based on SELECTED payouts only
                        if selected_payouts:
                            selected_payout_data = filtered_payouts.loc[selected_payouts]
                            total_gross = selected_payout_data['gross_amount'].sum()
                            total_processing_fees = selected_payout_data['processing_fee_amount'].sum()
                            total_net = selected_payout_data['net_payout_amount'].sum()
                        else:
                            # If no payouts selected, use zeros
                            total_gross = 0
                            total_processing_fees = 0
                            total_net = 0

                    # Show Journal vs Payout Comparison below the collapsible section (but above it in visibility)
                    if payment_type_totals:
                        st.markdown("### ⚖️ Journal vs Payout Comparison (Credit Card Only)")

                        # Filter for Credit Card payment types only (exclude gift cards)
                        credit_card_types = [pt for pt in payment_type_totals.keys() if
                                           ('credit' in pt.lower() or 'card' in pt.lower() or 'visa' in pt.lower() or 'mastercard' in pt.lower() or 'amex' in pt.lower())
                                           and 'gift' not in pt.lower()]

                        if not credit_card_types:
                            return

                        # Calculate first day refunds adjustment for credit cards
                        first_day_cc_refunds = calculate_first_day_credit_card_refunds(sales_df)

                        # Calculate totals for credit card transactions only
                        cc_payment_totals = {pt: amt for pt, amt in payment_type_totals.items() if pt in credit_card_types}
                        cc_processing_fees_totals = {pt: amt for pt, amt in processing_fees_totals.items() if pt in credit_card_types} if processing_fees_totals else {}
                        cc_net_payment_totals = {pt: amt for pt, amt in net_payment_totals.items() if pt in credit_card_types} if net_payment_totals else cc_payment_totals

                        # Create comparison table
                        comparison_data = []

                        # Journal payment types - use NET totals (after processing fees) for credit cards only
                        journal_gross_total = sum(cc_payment_totals.values())
                        journal_processing_fees_total = sum(cc_processing_fees_totals.values()) if cc_processing_fees_totals else 0
                        journal_net_total = sum(cc_net_payment_totals.values()) if cc_net_payment_totals else journal_gross_total

                        # Show gross payment totals (Credit Card only)
                        comparison_data.append({
                            'Source': f'{journal_version} Journal Export',
                            'Description': 'Credit Card Gross Totals',
                            'Amount': journal_gross_total,
                            'Details': ', '.join([f"{pt}: ${amt:,.2f}" for pt, amt in cc_payment_totals.items()])
                        })

                        # Show processing fees if available (Credit Card only)
                        if cc_processing_fees_totals and any(fee != 0 for fee in cc_processing_fees_totals.values()):
                            comparison_data.append({
                                'Source': f'{journal_version} Journal Export',
                                'Description': 'Credit Card Processing Fee Expenses',
                                'Amount': journal_processing_fees_total,
                                'Details': ', '.join([f"{pt}: ${fee:,.2f}" for pt, fee in cc_processing_fees_totals.items() if fee != 0])
                            })

                        # Show net payment totals (what should match payout) - Credit Card only
                        comparison_data.append({
                            'Source': f'{journal_version} Journal Export',
                            'Description': 'Credit Card Net Totals (After Fees)',
                            'Amount': journal_net_total,
                            'Details': ', '.join([f"{pt}: ${amt:,.2f}" for pt, amt in cc_net_payment_totals.items()]) if cc_net_payment_totals else 'Same as gross (no processing fees)'
                        })

                        # Add first day refunds adjustment if applicable
                        if first_day_cc_refunds > 0:
                            comparison_data.append({
                                'Source': f'{journal_version} Journal Export',
                                'Description': 'Plus: First Day Credit Card Refunds',
                                'Amount': first_day_cc_refunds,
                                'Details': f"Refunds processed on first day (add back to journal total)"
                            })

                            # Calculate adjusted journal net (ADD refunds back)
                            adjusted_journal_net = journal_net_total + first_day_cc_refunds
                            comparison_data.append({
                                'Source': f'{journal_version} Journal Export',
                                'Description': 'Adjusted Credit Card Net (Plus Refunds)',
                                'Amount': adjusted_journal_net,
                                'Details': f"${journal_net_total:,.2f} + ${first_day_cc_refunds:,.2f} first day refunds"
                            })
                        else:
                            adjusted_journal_net = journal_net_total

                        # Payout totals (now based on selected payouts only)
                        comparison_data.append({
                            'Source': 'Payout Report',
                            'Description': 'Net Payout Amount',
                            'Amount': total_net,
                            'Details': f"Gross: ${total_gross:,.2f}, Fees: ${total_processing_fees:,.2f}"
                        })

                        # Calculate difference using ADJUSTED journal totals (Credit Card only)
                        difference = adjusted_journal_net - total_net
                        comparison_data.append({
                            'Source': 'Difference',
                            'Description': 'Credit Card Journal Net - Payout Net',
                            'Amount': difference,
                            'Details': f"{'Journal higher' if difference > 0 else 'Payout higher'} by ${abs(difference):,.2f}"
                        })

                        # Display comparison table
                        comparison_df = pd.DataFrame(comparison_data)
                        comparison_df['Amount'] = comparison_df['Amount'].apply(lambda x: f"${x:,.2f}")

                        st.dataframe(
                            comparison_df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Source": st.column_config.TextColumn("Source", width="small"),
                                "Description": st.column_config.TextColumn("Description", width="medium"),
                                "Amount": st.column_config.TextColumn("Amount", width="small"),
                                "Details": st.column_config.TextColumn("Details", width="large"),
                            }
                        )

                        # Show detailed payment type breakdown (Credit Card only)
                        if len(cc_payment_totals) > 0:
                            pass  # Payment type breakdown removed
                            # Payment type breakdown table removed

                            # Excluded payment types info removed

                        # Analysis notes removed

                        # Show net comparison validation
                        if abs(difference) < 10:  # Within $10
                            st.success(f"✅ Credit Card Journal Net and Payout Net are closely matched (difference: ${abs(difference):,.2f})")
                        elif abs(difference) < 100:  # Within $100
                            st.info(f"ℹ️ Credit Card Journal Net and Payout Net are reasonably close (difference: ${abs(difference):,.2f})")
                        else:
                            st.warning(f"⚠️ Significant difference between Credit Card Journal Net and Payout Net (${abs(difference):,.2f}). Review for discrepancies.")

                        # Show processing fee validation if available (Credit Card only)
                        if cc_processing_fees_totals and any(fee != 0 for fee in cc_processing_fees_totals.values()):
                            journal_fees_total = abs(journal_processing_fees_total)
                            payout_fees_total = abs(total_processing_fees)
                            fee_difference = abs(journal_fees_total - payout_fees_total)

                            # Processing fee comparison (silent)
                    
            except Exception as e:
                st.error(f"❌ Error processing payout CSV: {str(e)}")
        elif payout_df is not None and not journal_available:
            pass  # No journal data available
        elif payout_df is None and journal_available:
            pass  # No payout data available
        elif payout_df is None and not journal_available:
            pass  # Neither data available
            
    except Exception as e:
        st.error(f"❌ Error in payout comparison section: {str(e)}")


def calculate_first_day_credit_card_refunds(df):
    """Calculate the net refund amount for credit card transactions on the first day of the sales period"""
    try:
        if df.empty or 'Created At Date' not in df.columns:
            return 0.0
        
        # Convert date column to datetime
        df_copy = df.copy()
        df_copy['Created At Date'] = pd.to_datetime(df_copy['Created At Date'], errors='coerce')
        
        # Get the first date in the dataset
        first_date = df_copy['Created At Date'].min()
        if pd.isna(first_date):
            return 0.0
        
        # Filter for first day refunds only
        first_day_refunds = df_copy[
            (df_copy['Created At Date'].dt.date == first_date.date()) &
            (df_copy['Payment or Refund'] == 'Refund') &
            (df_copy['Payment Type'].str.lower().str.contains('credit', na=False)) &
            (~df_copy['Payment Type'].str.lower().str.contains('gift', na=False))
        ].copy()
        
        if first_day_refunds.empty:
            return 0.0
        
        # Sum the "Refund Net" amounts (these should be negative)
        # Convert to numeric and handle any formatting issues
        refund_net_col = first_day_refunds['Refund Net'].astype(str).str.replace('$', '').str.replace(',', '').str.replace('"', '')
        refund_net_amounts = pd.to_numeric(refund_net_col, errors='coerce').fillna(0)
        total_first_day_refunds = refund_net_amounts.sum()
        
        # Return the absolute value since we want the positive adjustment amount
        return abs(total_first_day_refunds)
        
    except Exception as e:
        st.error(f"❌ Error calculating first day credit card refunds: {str(e)}")
        return 0.0

