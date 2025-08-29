# Main reconciliation view
import streamlit as st
import pandas as pd
from datetime import datetime
from scripts.config import NOTES_FILES
from scripts.auth import check_authentication
from scripts.data_loaders import load_fareharbour_data, load_fareharbour_payments_data, load_quickbooks_data
from scripts.comparers import find_missing_bookings, find_cancelled_vs_open, compare_amounts
from scripts.payment_comparers import compare_payments_refunds
from scripts.utils import (
    export_to_excel, void_invoices_in_quickbooks, load_notes_from_csv,
    save_notes_to_csv, merge_notes_with_data, create_notes_editor,
    save_table_notes, show_notes_file_info
)
from scripts.config import ENABLE_VOID_FEATURE

def main_reconciliation_view():
    """Main reconciliation page view"""
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
                    missing_notes_file = NOTES_FILES["missing_bookings"]
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
                                mime="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet"
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
                    cancelled_notes_file = NOTES_FILES["cancelled_vs_open"]
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
                                mime="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet"
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
                                                mime="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet"
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
                    existing_notes = load_notes_from_csv(NOTES_FILES["amount_differences"])

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
                            if save_notes_to_csv(notes_to_save, NOTES_FILES["amount_differences"]):
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
                                mime="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet"
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
                    if os.path.exists(NOTES_FILES["amount_differences"]):
                        file_stat = os.stat(NOTES_FILES["amount_differences"])
                        file_size = file_stat.st_size
                        file_modified = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                        with st.expander("📁 Notes File Information"):
                            st.write(f"**File:** {NOTES_FILES['amount_differences']}")
                            st.write(f"**Size:** {file_size} bytes")
                            st.write(f"**Last Modified:** {file_modified}")
                            st.write(f"**Total Saved Notes:** {len(existing_notes)}")

                            if st.button("🗑️ Clear All Notes"):
                                if os.path.exists(NOTES_FILES["amount_differences"]):
                                    os.remove(NOTES_FILES["amount_differences"])
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
                        payment_notes_file = NOTES_FILES["payment_refund"]
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
                                    mime="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet"
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
                    missing_notes = load_notes_from_csv(NOTES_FILES["missing_bookings"])
                    cancelled_notes = load_notes_from_csv(NOTES_FILES["cancelled_vs_open"])
                    amount_notes = load_notes_from_csv(NOTES_FILES["amount_differences"])

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
                        payment_notes = load_notes_from_csv(NOTES_FILES["payment_refund"])
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
                        (NOTES_FILES["missing_bookings"], "Missing Bookings"),
                        (NOTES_FILES["cancelled_vs_open"], "Cancelled vs Open"),
                        (NOTES_FILES["amount_differences"], "Amount Differences"),
                        (NOTES_FILES["payment_refund"], "Payment/Refund Comparison")
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
                        mime="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet"
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
