# Payment and refund comparison functions
import pandas as pd
import streamlit as st

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
