# Sales Report Analysis View
import streamlit as st
import pandas as pd
from datetime import datetime
from scripts.data_loaders import load_sales_csv_data
from scripts.database import execute_query

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
