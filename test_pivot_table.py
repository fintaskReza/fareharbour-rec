#!/usr/bin/env python3
"""
Test script to generate pivot table from Sales--test.csv
with proportional fee calculation based on partial payments
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
    print(f"Columns: {list(df.columns)}")
    
    # Clean currency columns
    currency_columns = [
        'Subtotal Paid', 'Tax Paid', 'Total Paid', 'Subtotal', 'Total Tax', 'Total'
    ]
    
    for col in currency_columns:
        if col in df.columns:
            df[col] = clean_currency_column(df[col])
    
    # Clean numeric columns
    if '# of Pax' in df.columns:
        df['# of Pax'] = pd.to_numeric(df['# of Pax'], errors='coerce').fillna(0)
    
    return df

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
    """
    if subtotal_total == 0:
        return 0
    
    proportion = subtotal_paid / subtotal_total
    return proportion * total_fees_for_booking

def create_pivot_table(df, fee_mappings_df):
    """Create the pivot table with Payment/Refund breakdown"""
    print("\nCreating pivot table...")
    
    pivot_data = []
    
    # Get unique tours
    tours = df['Item'].unique()
    print(f"Found {len(tours)} unique tours: {list(tours)}")
    
    # Process payments
    payments_df = df[df['Payment or Refund'] == 'Payment']
    print(f"\nProcessing {len(payments_df)} payments...")
    
    for tour in tours:
        tour_payments = payments_df[payments_df['Item'] == tour]
        if not tour_payments.empty:
            print(f"\n  Tour: {tour}")
            print(f"    Payments: {len(tour_payments)}")
            
            total_ex_fee_subtotal = 0
            total_proportional_fees = 0
            
            # Process each payment transaction
            for _, row in tour_payments.iterrows():
                subtotal_paid = row['Subtotal Paid']
                subtotal_total = row['Subtotal']  # Full booking subtotal
                guests = row['# of Pax']
                
                print(f"    Transaction: Subtotal Paid=${subtotal_paid}, Subtotal Total=${subtotal_total}, Guests={guests}")
                
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
                
                print(f"      Full booking fees: ${total_fees_for_booking:.2f}")
                print(f"      Proportional fees: ${proportional_fees:.2f}")
                print(f"      Ex-fee subtotal: ${ex_fee_subtotal:.2f}")
                
                total_ex_fee_subtotal += ex_fee_subtotal
                total_proportional_fees += proportional_fees
            
            print(f"    TOTAL - Ex-fee subtotal: ${total_ex_fee_subtotal:.2f}, Fees: ${total_proportional_fees:.2f}")
            
            pivot_data.append({
                'Payment or Refund': 'Payment',
                'Item': tour,
                'SUM of Ex fee sub paid': total_ex_fee_subtotal,
                'SUM of Fees': total_proportional_fees
            })
    
    # Process refunds
    refunds_df = df[df['Payment or Refund'] == 'Refund']
    print(f"\nProcessing {len(refunds_df)} refunds...")
    
    for tour in tours:
        tour_refunds = refunds_df[refunds_df['Item'] == tour]
        if not tour_refunds.empty:
            print(f"\n  Tour: {tour}")
            print(f"    Refunds: {len(tour_refunds)}")
            
            total_ex_fee_subtotal = 0
            total_proportional_fees = 0
            
            # Process each refund transaction
            for _, row in tour_refunds.iterrows():
                subtotal_paid = row['Subtotal Paid']  # This should be negative
                subtotal_total = abs(row['Subtotal'])  # Use absolute value for proportion calculation
                guests = abs(row['# of Pax'])  # Use absolute value
                
                print(f"    Transaction: Subtotal Paid=${subtotal_paid}, Subtotal Total=${subtotal_total}, Guests={guests}")
                
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
                
                print(f"      Full booking fees: ${total_fees_for_booking:.2f}")
                print(f"      Proportional fees: ${proportional_fees:.2f}")
                print(f"      Ex-fee subtotal: ${ex_fee_subtotal:.2f}")
                
                total_ex_fee_subtotal += ex_fee_subtotal
                total_proportional_fees += proportional_fees
            
            print(f"    TOTAL - Ex-fee subtotal: ${total_ex_fee_subtotal:.2f}, Fees: ${total_proportional_fees:.2f}")
            
            pivot_data.append({
                'Payment or Refund': 'Refund',
                'Item': tour,
                'SUM of Ex fee sub paid': total_ex_fee_subtotal,
                'SUM of Fees': total_proportional_fees
            })
    
    # Convert to DataFrame
    pivot_df = pd.DataFrame(pivot_data)
    
    if pivot_df.empty:
        print("No data for pivot table")
        return pd.DataFrame()
    
    # Calculate totals
    payment_data = pivot_df[pivot_df['Payment or Refund'] == 'Payment']
    refund_data = pivot_df[pivot_df['Payment or Refund'] == 'Refund']
    
    payment_totals = {
        'SUM of Ex fee sub paid': payment_data['SUM of Ex fee sub paid'].sum() if not payment_data.empty else 0,
        'SUM of Fees': payment_data['SUM of Fees'].sum() if not payment_data.empty else 0
    }
    
    refund_totals = {
        'SUM of Ex fee sub paid': refund_data['SUM of Ex fee sub paid'].sum() if not refund_data.empty else 0,
        'SUM of Fees': refund_data['SUM of Fees'].sum() if not refund_data.empty else 0
    }
    
    # Add total rows
    total_rows = [
        {
            'Payment or Refund': 'Payment Total',
            'Item': '',
            'SUM of Ex fee sub paid': payment_totals['SUM of Ex fee sub paid'],
            'SUM of Fees': payment_totals['SUM of Fees']
        },
        {
            'Payment or Refund': 'Refund Total',
            'Item': '',
            'SUM of Ex fee sub paid': refund_totals['SUM of Ex fee sub paid'],
            'SUM of Fees': refund_totals['SUM of Fees']
        },
        {
            'Payment or Refund': 'Grand Total',
            'Item': '',
            'SUM of Ex fee sub paid': payment_totals['SUM of Ex fee sub paid'] + refund_totals['SUM of Ex fee sub paid'],
            'SUM of Fees': payment_totals['SUM of Fees'] + refund_totals['SUM of Fees']
        }
    ]
    
    for total_row in total_rows:
        pivot_df = pd.concat([pivot_df, pd.DataFrame([total_row])], ignore_index=True)
    
    return pivot_df

def format_and_display_table(pivot_df):
    """Format and display the pivot table"""
    if pivot_df.empty:
        print("No data to display")
        return
    
    print("\n" + "="*80)
    print("PIVOT TABLE RESULTS")
    print("="*80)
    
    # Format for display
    display_df = pivot_df.copy()
    
    # Format currency columns
    for col in ['SUM of Ex fee sub paid', 'SUM of Fees']:
        display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "0")
    
    # Print table
    print(f"{'Payment or Refund':<20} {'Item':<35} {'SUM of Ex fee sub paid':<20} {'SUM of Fees':<15}")
    print("-" * 90)
    
    for _, row in display_df.iterrows():
        payment_refund = str(row['Payment or Refund'])[:19]
        item = str(row['Item'])[:34]
        ex_fee = str(row['SUM of Ex fee sub paid'])
        fees = str(row['SUM of Fees'])
        
        # Highlight total rows
        if 'Total' in payment_refund:
            print(f"{payment_refund:<20} {item:<35} {ex_fee:<20} {fees:<15}")
        else:
            print(f"{payment_refund:<20} {item:<35} {ex_fee:<20} {fees:<15}")
    
    print("="*80)

def main():
    """Main function"""
    csv_path = "Sales--test.csv"
    
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found")
        return
    
    # Load and clean data
    df = load_and_clean_data(csv_path)
    
    # Get fee mappings
    fee_mappings_df = get_fee_mappings()
    
    if fee_mappings_df.empty:
        print("Warning: No fee mappings available. Fees will be calculated as 0.")
    else:
        print(f"Loaded {len(fee_mappings_df)} fee mappings")
        print("Fee mappings:")
        for _, row in fee_mappings_df.iterrows():
            print(f"  {row['tour_name']}: {row['fee_name']} = ${row['per_person_amount']}")
    
    # Create pivot table
    pivot_df = create_pivot_table(df, fee_mappings_df)
    
    # Display results
    format_and_display_table(pivot_df)
    
    # Save to CSV
    output_file = "pivot_table_results.csv"
    pivot_df.to_csv(output_file, index=False)
    print(f"\nResults saved to {output_file}")

if __name__ == "__main__":
    main()

