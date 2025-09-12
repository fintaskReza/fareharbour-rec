#!/usr/bin/env python3
"""
Test script to generate V2 pivot table from Sales--test.csv
with V2 filtering (excludes affiliate amounts received/receivable) 
and proportional fee calculation based on partial payments
"""

import pandas as pd
import sys
import os

# Add the project directory to Python path to import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.database import execute_query

def clean_currency_column(series):
    """Clean currency columns by removing $ signs and converting to numeric"""
    if series.dtype == 'object':
        # Handle negative values properly
        series = series.astype(str)
        # Check if value starts with negative sign and preserve it
        is_negative = series.str.startswith('-')
        # Remove currency symbols and commas
        series = series.str.replace('[$,"]', '', regex=True)
        # Remove any remaining negative signs
        series = series.str.replace('-', '', regex=False)
        # Convert to numeric
        series = pd.to_numeric(series, errors='coerce').fillna(0)
        # Apply negative sign back where needed
        series = series.where(~is_negative, -series)
    return pd.to_numeric(series, errors='coerce').fillna(0)

def load_and_clean_data(csv_path):
    """Load and clean the CSV data"""
    print(f"Loading data from {csv_path}...")
    
    # Read CSV starting from row 2 (skip the first header row)
    df = pd.read_csv(csv_path, skiprows=1)
    
    print(f"Loaded {len(df)} rows")
    
    # Clean currency columns
    currency_columns = [
        'Subtotal Paid', 'Tax Paid', 'Total Paid', 'Subtotal', 'Total Tax', 'Total',
        'Receivable from Affiliate', 'Received from Affiliate'
    ]
    
    for col in currency_columns:
        if col in df.columns:
            df[col] = clean_currency_column(df[col])
    
    # Clean numeric columns
    if '# of Pax' in df.columns:
        df['# of Pax'] = pd.to_numeric(df['# of Pax'], errors='coerce').fillna(0)
    
    return df

def apply_v2_filter(df):
    """
    Apply V2 filtering logic: exclude bookings where affiliate amounts received/receivable > 0
    This implements your Excel formula: =if(sum(BJ11:BK11)>0,0,1)
    """
    print("\nApplying V2 filter...")
    
    original_count = len(df)
    
    # Calculate sum of Receivable from Affiliate + Received from Affiliate
    df['Affiliate_Sum'] = df['Receivable from Affiliate'] + df['Received from Affiliate']
    
    # V2 filter: exclude bookings where affiliate sum > 0
    v2_filtered_df = df[df['Affiliate_Sum'] <= 0].copy()
    
    excluded_count = original_count - len(v2_filtered_df)
    
    print(f"Original bookings: {original_count}")
    print(f"Excluded by V2 filter: {excluded_count}")
    print(f"V2 filtered bookings: {len(v2_filtered_df)}")
    
    # Show some examples of excluded bookings
    excluded_df = df[df['Affiliate_Sum'] > 0]
    if not excluded_df.empty:
        print(f"\nSample excluded bookings:")
        for _, row in excluded_df.head(3).iterrows():
            print(f"  {row['Item']}: Receivable=${row['Receivable from Affiliate']:.2f}, Received=${row['Received from Affiliate']:.2f}")
    
    return v2_filtered_df

def get_fee_mappings():
    """Get fee mappings from database"""
    try:
        fee_mappings = execute_query("""
            SELECT t.name as tour_name, f.name as fee_name, f.per_person_amount
            FROM tour_fees tf
            JOIN tours t ON tf.tour_id = t.id
            JOIN fees f ON tf.fee_id = f.id
            ORDER BY t.name, f.name
        """)
        
        if fee_mappings:
            fee_mappings_df = pd.DataFrame(fee_mappings, columns=['tour_name', 'fee_name', 'per_person_amount'])
            fee_mappings_df['per_person_amount'] = pd.to_numeric(fee_mappings_df['per_person_amount'], errors='coerce').fillna(0)
            return fee_mappings_df
        else:
            print("No fee mappings found in database")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error getting fee mappings: {e}")
        return pd.DataFrame()

def calculate_proportional_fees(subtotal_paid, subtotal_total, total_fees_for_booking):
    """
    Calculate proportional fees based on partial payment
    Formula: (Subtotal Paid / Subtotal Total) * Total Fees
    
    Special cases:
    - If subtotal_total is 0, return 0
    - If payment >= subtotal (overpayment), cap proportion at 1.0 (100% of fees)
    """
    if subtotal_total == 0:
        return 0
    
    proportion = subtotal_paid / subtotal_total
    
    # Cap proportion at 1.0 for overpayment scenarios
    # This prevents fees from being more than 100% of the total booking fees
    proportion = min(proportion, 1.0)
    
    return proportion * total_fees_for_booking

def create_v2_pivot_table(df, fee_mappings_df):
    """Create the V2 pivot table with Payment/Refund breakdown"""
    print("\nCreating V2 pivot table...")
    print("=== DEBUGGING: PARTIAL PAYMENTS & FULL PAYMENTS ===")

    pivot_data = []
    payment_debug_count = 0
    refund_debug_count = 0
    partial_payment_debug_count = 0
    max_debug = 3
    max_partial_debug = 5

    # Get unique tours
    tours = df['Item'].unique()
    print(f"Found {len(tours)} unique tours: {list(tours)}")
    print(f"Total transactions: {len(df)}")

    # Process payments
    payments_df = df[df['Payment or Refund'] == 'Payment']
    print(f"\nProcessing {len(payments_df)} V2 payments...")
    
    for tour in tours:
        tour_payments = payments_df[payments_df['Item'] == tour]
        if not tour_payments.empty:
            print(f"\n  Tour: {tour}")
            print(f"    V2 Payments: {len(tour_payments)}")

            total_ex_fee_subtotal = 0
            total_proportional_fees = 0
            total_raw_subtotal_paid = 0
            booking_count = len(tour_payments)

            # Process each payment transaction
            for _, row in tour_payments.iterrows():
                subtotal_paid = row['Subtotal Paid']
                subtotal_total = row['Subtotal']  # Full booking subtotal
                guests = row['# of Pax']

                # Add to raw subtotal total
                total_raw_subtotal_paid += subtotal_paid

                # Calculate total fees for this booking (full booking)
                total_fees_for_booking = 0
                if not fee_mappings_df.empty:
                    tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour]
                    for _, fee_row in tour_fees.iterrows():
                        total_fees_for_booking += fee_row['per_person_amount'] * guests

                # Calculate proportional fees based on payment amount
                proportional_fees = calculate_proportional_fees(subtotal_paid, subtotal_total, total_fees_for_booking)

                # Ex-fee subtotal = Subtotal Paid - Proportional Fees
                ex_fee_subtotal = subtotal_paid - proportional_fees

                # Check if this is a partial payment
                is_partial_payment = abs(subtotal_paid - subtotal_total) > 0.01
                
                # Debug output for first 3 full payments
                if payment_debug_count < max_debug and not is_partial_payment:
                    print(f"\n--- FULL PAYMENT #{payment_debug_count + 1} DEBUG ---")
                    print(f"Payment or Refund ID: {row['Payment or Refund ID']}")
                    print(f"Tour: {tour}")
                    print(f"Payment or Refund: Payment")
                    print(f"Guests: {guests}")
                    print(f"Subtotal Paid: ${subtotal_paid:.2f}")
                    print(f"Full Subtotal: ${subtotal_total:.2f}")
                    print(f"Full Booking Fees: ${total_fees_for_booking:.2f}")
                    print(f"Proportion: {subtotal_paid/subtotal_total:.4f}")
                    print(f"Proportional Fees: ${proportional_fees:.2f}")
                    print(f"Ex-fee Subtotal: ${ex_fee_subtotal:.2f}")
                    print(f"Raw Subtotal Paid: ${subtotal_paid:.2f}")
                    print("------------------------------")
                    payment_debug_count += 1
                
                # Debug output for partial payments
                elif partial_payment_debug_count < max_partial_debug and is_partial_payment:
                    print(f"\n--- PARTIAL PAYMENT #{partial_payment_debug_count + 1} DEBUG ---")
                    print(f"Payment or Refund ID: {row['Payment or Refund ID']}")
                    print(f"Tour: {tour}")
                    print(f"Payment or Refund: Payment")
                    print(f"Guests: {guests}")
                    print(f"Subtotal Paid: ${subtotal_paid:.2f}")
                    print(f"Full Subtotal: ${subtotal_total:.2f}")
                    print(f"Full Booking Fees: ${total_fees_for_booking:.2f}")
                    print(f"Proportion: {subtotal_paid/subtotal_total:.4f} ⚠️ PARTIAL")
                    print(f"Proportional Fees: ${proportional_fees:.2f}")
                    print(f"Ex-fee Subtotal: ${ex_fee_subtotal:.2f}")
                    print(f"Raw Subtotal Paid: ${subtotal_paid:.2f}")
                    print("------------------------------")
                    partial_payment_debug_count += 1

                total_ex_fee_subtotal += ex_fee_subtotal
                total_proportional_fees += proportional_fees

            print(f"    TOTAL - Ex-fee subtotal: ${total_ex_fee_subtotal:.2f}, Fees: ${total_proportional_fees:.2f}, Raw subtotal: ${total_raw_subtotal_paid:.2f}")

            pivot_data.append({
                'Payment or Refund': 'Payment',
                'Item': tour,
                'Count': booking_count,
                'SUM of Ex fee sub paid': total_ex_fee_subtotal,
                'SUM of Fees': total_proportional_fees,
                'Total Raw Subtotal Paid': total_raw_subtotal_paid,
                'Fee + Ex fee subtotal': total_ex_fee_subtotal + total_proportional_fees
            })
    
    # Process refunds
    refunds_df = df[df['Payment or Refund'] == 'Refund']
    print(f"\nProcessing {len(refunds_df)} V2 refunds...")
    
    for tour in tours:
        tour_refunds = refunds_df[refunds_df['Item'] == tour]
        if not tour_refunds.empty:
            print(f"\n  Tour: {tour}")
            print(f"    V2 Refunds: {len(tour_refunds)}")

            total_ex_fee_subtotal = 0
            total_proportional_fees = 0
            total_raw_subtotal_paid = 0
            booking_count = len(tour_refunds)

            # Process each refund transaction
            for _, row in tour_refunds.iterrows():
                subtotal_paid = row['Subtotal Paid']  # This should be negative
                subtotal_total = abs(row['Subtotal'])  # Use absolute value for proportion calculation
                guests = abs(row['# of Pax'])  # Use absolute value

                # Add to raw subtotal total
                total_raw_subtotal_paid += subtotal_paid

                # Calculate total fees for this booking (full booking)
                total_fees_for_booking = 0
                if not fee_mappings_df.empty:
                    tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour]
                    for _, fee_row in tour_fees.iterrows():
                        total_fees_for_booking += fee_row['per_person_amount'] * guests

                # Calculate proportional fees based on refund amount
                proportional_fees = calculate_proportional_fees(abs(subtotal_paid), subtotal_total, total_fees_for_booking)
                proportional_fees = -proportional_fees  # Make negative for refunds

                # For refunds: Ex-fee subtotal = Subtotal Paid + |Proportional Fees|
                # (since subtotal_paid is negative and we're adding back the fee portion)
                ex_fee_subtotal = subtotal_paid + abs(proportional_fees)

                # Debug output for first 3 refunds
                if refund_debug_count < max_debug:
                    print(f"\n--- REFUND #{refund_debug_count + 1} DEBUG ---")
                    print(f"Payment or Refund ID: {row['Payment or Refund ID']}")
                    print(f"Tour: {tour}")
                    print(f"Payment or Refund: Refund")
                    print(f"Guests: {guests}")
                    print(f"Subtotal Paid: ${subtotal_paid:.2f}")
                    print(f"Full Subtotal: ${row['Subtotal']:.2f}")
                    print(f"Full Booking Fees: ${total_fees_for_booking:.2f}")
                    print(f"Proportion: {abs(subtotal_paid)/subtotal_total:.4f}")
                    print(f"Proportional Fees: ${proportional_fees:.2f}")
                    print(f"Ex-fee Subtotal: ${ex_fee_subtotal:.2f}")
                    print(f"Raw Subtotal Paid: ${subtotal_paid:.2f}")
                    print("------------------------------")
                    refund_debug_count += 1

                total_ex_fee_subtotal += ex_fee_subtotal
                total_proportional_fees += proportional_fees

            print(f"    TOTAL - Ex-fee subtotal: ${total_ex_fee_subtotal:.2f}, Fees: ${total_proportional_fees:.2f}, Raw subtotal: ${total_raw_subtotal_paid:.2f}")

            pivot_data.append({
                'Payment or Refund': 'Refund',
                'Item': tour,
                'Count': booking_count,
                'SUM of Ex fee sub paid': total_ex_fee_subtotal,
                'SUM of Fees': total_proportional_fees,
                'Total Raw Subtotal Paid': total_raw_subtotal_paid,
                'Fee + Ex fee subtotal': total_ex_fee_subtotal + total_proportional_fees
            })
    
    # Convert to DataFrame
    pivot_df = pd.DataFrame(pivot_data)
    
    if pivot_df.empty:
        print("No data for V2 pivot table")
        return pd.DataFrame()
    
    # Calculate totals
    payment_data = pivot_df[pivot_df['Payment or Refund'] == 'Payment']
    refund_data = pivot_df[pivot_df['Payment or Refund'] == 'Refund']
    
    payment_totals = {
        'Count': payment_data['Count'].sum() if not payment_data.empty else 0,
        'SUM of Ex fee sub paid': payment_data['SUM of Ex fee sub paid'].sum() if not payment_data.empty else 0,
        'SUM of Fees': payment_data['SUM of Fees'].sum() if not payment_data.empty else 0,
        'Total Raw Subtotal Paid': payment_data['Total Raw Subtotal Paid'].sum() if not payment_data.empty else 0,
        'Fee + Ex fee subtotal': payment_data['Fee + Ex fee subtotal'].sum() if not payment_data.empty else 0
    }

    refund_totals = {
        'Count': refund_data['Count'].sum() if not refund_data.empty else 0,
        'SUM of Ex fee sub paid': refund_data['SUM of Ex fee sub paid'].sum() if not refund_data.empty else 0,
        'SUM of Fees': refund_data['SUM of Fees'].sum() if not refund_data.empty else 0,
        'Total Raw Subtotal Paid': refund_data['Total Raw Subtotal Paid'].sum() if not refund_data.empty else 0,
        'Fee + Ex fee subtotal': refund_data['Fee + Ex fee subtotal'].sum() if not refund_data.empty else 0
    }
    
    # Add total rows
    total_rows = [
        {
            'Payment or Refund': 'Payment Total',
            'Item': '',
            'Count': payment_totals['Count'],
            'SUM of Ex fee sub paid': payment_totals['SUM of Ex fee sub paid'],
            'SUM of Fees': payment_totals['SUM of Fees'],
            'Total Raw Subtotal Paid': payment_totals['Total Raw Subtotal Paid'],
            'Fee + Ex fee subtotal': payment_totals['Fee + Ex fee subtotal']
        },
        {
            'Payment or Refund': 'Refund Total',
            'Item': '',
            'Count': refund_totals['Count'],
            'SUM of Ex fee sub paid': refund_totals['SUM of Ex fee sub paid'],
            'SUM of Fees': refund_totals['SUM of Fees'],
            'Total Raw Subtotal Paid': refund_totals['Total Raw Subtotal Paid'],
            'Fee + Ex fee subtotal': refund_totals['Fee + Ex fee subtotal']
        },
        {
            'Payment or Refund': 'Grand Total',
            'Item': '',
            'Count': payment_totals['Count'] + refund_totals['Count'],
            'SUM of Ex fee sub paid': payment_totals['SUM of Ex fee sub paid'] + refund_totals['SUM of Ex fee sub paid'],
            'SUM of Fees': payment_totals['SUM of Fees'] + refund_totals['SUM of Fees'],
            'Total Raw Subtotal Paid': payment_totals['Total Raw Subtotal Paid'] + refund_totals['Total Raw Subtotal Paid'],
            'Fee + Ex fee subtotal': payment_totals['Fee + Ex fee subtotal'] + refund_totals['Fee + Ex fee subtotal']
        }
    ]
    
    for total_row in total_rows:
        pivot_df = pd.concat([pivot_df, pd.DataFrame([total_row])], ignore_index=True)
    
    return pivot_df

def format_and_display_table(pivot_df, title="V2 PIVOT TABLE RESULTS"):
    """Format and display the pivot table"""
    if pivot_df.empty:
        print("No data to display")
        return
    
    print("\n" + "="*80)
    print(title)
    print("="*80)
    
    # Format for display
    display_df = pivot_df.copy()
    
    # Format currency columns - round to nearest 1 for display only
    for col in ['SUM of Ex fee sub paid', 'SUM of Fees', 'Total Raw Subtotal Paid', 'Fee + Ex fee subtotal']:
        display_df[col] = display_df[col].apply(lambda x: f"{round(x):,.0f}" if pd.notnull(x) else "0")

    # Format count column
    display_df['Count'] = display_df['Count'].apply(lambda x: f"{int(x):,d}" if pd.notnull(x) else "0")

    # Print table
    print(f"{'Payment or Refund':<20} {'Item':<25} {'Count':<8} {'Ex fee sub':<12} {'Fees':<8} {'Raw Sub Paid':<12} {'Fee+Sub':<10}")
    print("-" * 95)

    for _, row in display_df.iterrows():
        payment_refund = str(row['Payment or Refund'])[:19]
        item = str(row['Item'])[:24]
        count = str(row['Count'])
        ex_fee = str(row['SUM of Ex fee sub paid'])
        fees = str(row['SUM of Fees'])
        raw_sub = str(row['Total Raw Subtotal Paid'])
        fee_plus_sub = str(row['Fee + Ex fee subtotal'])

        # Highlight total rows
        if 'Total' in payment_refund:
            print(f"{payment_refund:<20} {item:<25} {count:<8} {ex_fee:<12} {fees:<8} {raw_sub:<12} {fee_plus_sub:<10}")
        else:
            print(f"{payment_refund:<20} {item:<25} {count:<8} {ex_fee:<12} {fees:<8} {raw_sub:<12} {fee_plus_sub:<10}")
    
    print("="*80)

def main():
    """Main function"""
    csv_path = "Sales--test.csv"
    
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found")
        return
    
    # Load and clean data
    df = load_and_clean_data(csv_path)
    
    # Apply V2 filter (your Excel formula logic)
    v2_filtered_df = apply_v2_filter(df)
    
    # Get fee mappings
    fee_mappings_df = get_fee_mappings()
    
    if fee_mappings_df.empty:
        print("Warning: No fee mappings available. Fees will be calculated as 0.")
    else:
        print(f"Loaded {len(fee_mappings_df)} fee mappings")
    
    # Create V2 pivot table
    v2_pivot_df = create_v2_pivot_table(v2_filtered_df, fee_mappings_df)
    
    # Display V2 results
    format_and_display_table(v2_pivot_df, "V2 PIVOT TABLE RESULTS (WITH AFFILIATE FILTERING)")
    
    # For comparison, also create V1 (no filtering)
    print(f"\n" + "="*80)
    print("COMPARISON: V1 vs V2")
    print("="*80)
    
    v1_pivot_df = create_v2_pivot_table(df, fee_mappings_df)  # Use original data
    
    # Compare totals
    v1_totals = v1_pivot_df[v1_pivot_df['Payment or Refund'] == 'Grand Total']
    v2_totals = v2_pivot_df[v2_pivot_df['Payment or Refund'] == 'Grand Total']
    
    if not v1_totals.empty and not v2_totals.empty:
        v1_count = v1_totals.iloc[0]['Count']
        v1_ex_fee = v1_totals.iloc[0]['SUM of Ex fee sub paid']
        v1_fees = v1_totals.iloc[0]['SUM of Fees']
        v1_raw_sub = v1_totals.iloc[0]['Total Raw Subtotal Paid']
        v1_combined = v1_totals.iloc[0]['Fee + Ex fee subtotal']

        v2_count = v2_totals.iloc[0]['Count']
        v2_ex_fee = v2_totals.iloc[0]['SUM of Ex fee sub paid']
        v2_fees = v2_totals.iloc[0]['SUM of Fees']
        v2_raw_sub = v2_totals.iloc[0]['Total Raw Subtotal Paid']
        v2_combined = v2_totals.iloc[0]['Fee + Ex fee subtotal']

        print(f"V1 (All bookings):")
        print(f"  Count: {v1_count:,.0f}")
        print(f"  Raw subtotal paid: ${v1_raw_sub:,.2f}")
        print(f"  Ex-fee subtotal: ${v1_ex_fee:,.2f}")
        print(f"  Fees: ${v1_fees:,.2f}")
        print(f"  Fee + ex-fee subtotal: ${v1_combined:,.2f}")

        print(f"V2 (Filtered bookings):")
        print(f"  Count: {v2_count:,.0f}")
        print(f"  Raw subtotal paid: ${v2_raw_sub:,.2f}")
        print(f"  Ex-fee subtotal: ${v2_ex_fee:,.2f}")
        print(f"  Fees: ${v2_fees:,.2f}")
        print(f"  Fee + ex-fee subtotal: ${v2_combined:,.2f}")

        print(f"Difference:")
        print(f"  Count: {v1_count - v2_count:,.0f}")
        print(f"  Raw subtotal paid: ${v1_raw_sub - v2_raw_sub:,.2f}")
        print(f"  Ex-fee subtotal: ${v1_ex_fee - v2_ex_fee:,.2f}")
        print(f"  Fees: ${v1_fees - v2_fees:,.2f}")
        print(f"  Fee + ex-fee subtotal: ${v1_combined - v2_combined:,.2f}")
    
    # Save results
    output_file = "v2_pivot_table_results.csv"
    v2_pivot_df.to_csv(output_file, index=False)
    print(f"\nV2 results saved to {output_file}")

if __name__ == "__main__":
    main()
