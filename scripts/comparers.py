# Comparison and analysis functions
import pandas as pd
import streamlit as st
import re

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
