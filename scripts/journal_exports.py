"""
Journal Export Functions for FareHarbour Sales Analysis

This module contains all journal export functionality including:
- V1 Journal Export (original logic)
- V2 Journal Export (excludes affiliate payments received)
- Detailed records breakdown
- Fee calculations and VAT handling
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from scripts.database import execute_query


def create_enhanced_quickbooks_journal(pivot_df, raw_df, include_processing_fees=False):
    """Create enhanced QuickBooks journal entries with proper account mappings and VAT handling"""
    try:
        journal_entries = []
        entry_date = datetime.now().strftime('%Y-%m-%d')

        # Retrieve QuickBooks account mappings
        qb_mappings = get_quickbooks_mappings()

        # Get fee mappings for detailed breakdown
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

        entry_number = 1
        total_vat_amount = 0

        # Separate affiliate and direct bookings from raw_df
        affiliate_bookings = raw_df[raw_df['Affiliate'].notna() & (raw_df['Affiliate'] != '')].copy()
        direct_bookings = raw_df[~(raw_df['Affiliate'].notna() & (raw_df['Affiliate'] != ''))].copy()

        # Separate payments and refunds
        payments_df = raw_df[raw_df['Payment or Refund'] == 'Payment'].copy()
        refunds_df = raw_df[raw_df['Payment or Refund'] == 'Refund'].copy()

        # Calculate total VAT from direct bookings - separate payments and refunds
        payments_only_df = direct_bookings[direct_bookings['Payment or Refund'] == 'Payment']
        refunds_only_df = direct_bookings[direct_bookings['Payment or Refund'] == 'Refund']

        total_vat_payments = 0
        total_vat_refunds = 0

        if not payments_only_df.empty and 'Tax Paid' in payments_only_df.columns:
            total_vat_payments = pd.to_numeric(payments_only_df['Tax Paid'], errors='coerce').fillna(0).sum()

        if not refunds_only_df.empty and 'Tax Paid' in refunds_only_df.columns:
            # Refunds are negative, so we take absolute value for VAT refunds
            total_vat_refunds = abs(pd.to_numeric(refunds_only_df['Tax Paid'], errors='coerce').fillna(0).sum())

        total_vat_amount = total_vat_payments  # Only use payment VAT for journal entry

        # Calculate affiliate commissions and payables/receivables
        affiliate_commissions = {}
        affiliate_payables = {}
        affiliate_receivables = {}

        if not affiliate_bookings.empty:
            for _, row in affiliate_bookings.iterrows():
                affiliate_name = row.get('Affiliate', 'Unknown Affiliate')
                total_paid = pd.to_numeric(row.get('Total Paid', 0), errors='coerce')
                payable_to_affiliate = pd.to_numeric(row.get('Payable to Affiliate', 0), errors='coerce')
                paid_to_affiliate = pd.to_numeric(row.get('Paid to Affiliate', 0), errors='coerce')
                receivable_from_affiliate = pd.to_numeric(row.get('Receivable from Affiliate', 0), errors='coerce')
                received_from_affiliate = pd.to_numeric(row.get('Received from Affiliate', 0), errors='coerce')

                commission_expense = 0

                # Scenario 1: Affiliate collects payment (we have receivable from them)
                if receivable_from_affiliate > 0 or received_from_affiliate > 0:
                    # Commission = Total Paid - Affiliate Collection
                    affiliate_collection = receivable_from_affiliate + received_from_affiliate
                    commission_expense = total_paid - affiliate_collection

                    # Track receivables (affiliate collected payment, owes us the difference)
                    if affiliate_name in affiliate_receivables:
                        affiliate_receivables[affiliate_name] += affiliate_collection
                    else:
                        affiliate_receivables[affiliate_name] = affiliate_collection

                # Scenario 2: We collect payment (we pay commission to affiliate)
                elif payable_to_affiliate > 0 or paid_to_affiliate > 0:
                    commission_expense = payable_to_affiliate + paid_to_affiliate

                    # Track payables (we collected payment, owe commission to affiliate)
                    affiliate_payment = payable_to_affiliate + paid_to_affiliate
                    if affiliate_name in affiliate_payables:
                        affiliate_payables[affiliate_name] += affiliate_payment
                    else:
                        affiliate_payables[affiliate_name] = affiliate_payment

                # Track commission expense by affiliate
                if commission_expense > 0:
                    if affiliate_name in affiliate_commissions:
                        affiliate_commissions[affiliate_name] += commission_expense
                    else:
                        affiliate_commissions[affiliate_name] = commission_expense

        # Calculate total payments by payment type from ALL bookings
        total_payments_by_type = {}
        total_processing_fees_by_type = {}  # Track processing fees separately

        # Process DIRECT bookings payments
        for _, row in pivot_df.iterrows():
            tour_name = row['Tour Name']
            # Only use direct booking transactions for payments
            tour_transactions = direct_bookings[direct_bookings['Item'] == tour_name].copy()

            if not tour_transactions.empty:
                # Calculate payment breakdown using Subtotal Paid + Tax Paid
                tour_payment_breakdown = {}
                tour_processing_fee_breakdown = {}
                
                for _, transaction in tour_transactions.iterrows():
                    payment_type = transaction.get('Payment Type', 'Unknown')
                    subtotal_paid = pd.to_numeric(transaction.get('Subtotal Paid', 0), errors='coerce')
                    tax_paid = pd.to_numeric(transaction.get('Tax Paid', 0), errors='coerce')
                    processing_fee = pd.to_numeric(transaction.get('Processing Fee', 0), errors='coerce')
                    
                    # Base payment amount (always use gross amount for clearing accounts)
                    base_payment = subtotal_paid + tax_paid

                    # Always use gross payment amount for clearing accounts
                    # Processing fees will be handled as separate credit entries
                    
                    # Aggregate payment amounts (gross)
                    if payment_type in tour_payment_breakdown:
                        tour_payment_breakdown[payment_type] += base_payment
                    else:
                        tour_payment_breakdown[payment_type] = base_payment
                    
                    # Aggregate processing fees if enabled
                    if include_processing_fees and processing_fee != 0:
                        if payment_type in tour_processing_fee_breakdown:
                            tour_processing_fee_breakdown[payment_type] += processing_fee
                        else:
                            tour_processing_fee_breakdown[payment_type] = processing_fee

                # Add to overall totals
                for payment_type, amount in tour_payment_breakdown.items():
                    if payment_type in total_payments_by_type:
                        total_payments_by_type[payment_type] += amount
                    else:
                        total_payments_by_type[payment_type] = amount
                
                # Add processing fees to overall totals
                for payment_type, fee_amount in tour_processing_fee_breakdown.items():
                    if payment_type in total_processing_fees_by_type:
                        total_processing_fees_by_type[payment_type] += fee_amount
                    else:
                        total_processing_fees_by_type[payment_type] = fee_amount

        # Process AFFILIATE bookings payments as separate payment types
        affiliate_payments_by_type = {}
        if not affiliate_bookings.empty:
            for _, row in affiliate_bookings.iterrows():
                affiliate_name = row.get('Affiliate', 'Unknown Affiliate')
                payment_type = row.get('Payment Type', 'Unknown')

                # For affiliate payments, capture both Received and Receivable amounts
                received_from_affiliate = pd.to_numeric(row.get('Received from Affiliate', 0), errors='coerce')
                receivable_from_affiliate = pd.to_numeric(row.get('Receivable from Affiliate', 0), errors='coerce')
                paid_to_affiliate = pd.to_numeric(row.get('Paid to Affiliate', 0), errors='coerce')
                payable_to_affiliate = pd.to_numeric(row.get('Payable to Affiliate', 0), errors='coerce')

                # Total affiliate payment received/collected
                total_affiliate_payment = received_from_affiliate + receivable_from_affiliate

                # If there are payments received from affiliate, create affiliate payment type
                if total_affiliate_payment > 0:
                    affiliate_payment_type = f'Affiliate Payment - {affiliate_name}'
                    if affiliate_payment_type in affiliate_payments_by_type:
                        affiliate_payments_by_type[affiliate_payment_type] += total_affiliate_payment
                    else:
                        affiliate_payments_by_type[affiliate_payment_type] = total_affiliate_payment

            # Add affiliate payments to total payments
            for affiliate_payment_type, payment_amount in affiliate_payments_by_type.items():
                if affiliate_payment_type in total_payments_by_type:
                    total_payments_by_type[affiliate_payment_type] += payment_amount
                else:
                    total_payments_by_type[affiliate_payment_type] = payment_amount

        # Create ONE consolidated journal entry
        je_number = f'JE{entry_number:04d}'

        # Fee calculation is now done separately for payments and refunds below

        # REVENUE SIDE (Credits) - Generate directly from CSV records, not pivot tables
        
        # 1. Direct Tour Revenue - PAYMENTS (Credits)
        direct_payments = direct_bookings[direct_bookings['Payment or Refund'] == 'Payment']
        payment_revenue_by_tour = {}
        
        for _, row in direct_payments.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            # Calculate fees for this booking
            tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name] if not fee_mappings_df.empty else pd.DataFrame()
            booking_fee_amount = 0
            
            if not tour_fees.empty:
                for _, fee_row in tour_fees.iterrows():
                    fee_amount = fee_row['per_person_amount'] * guests
                    booking_fee_amount += fee_amount
            
            # Tour revenue for this booking = Subtotal Paid - Fees
            booking_tour_revenue = subtotal_paid - booking_fee_amount
            
            if booking_tour_revenue > 0:
                if tour_name in payment_revenue_by_tour:
                    payment_revenue_by_tour[tour_name] += booking_tour_revenue
                else:
                    payment_revenue_by_tour[tour_name] = booking_tour_revenue
        
        # Create payment revenue entries
        for tour_name, total_revenue in payment_revenue_by_tour.items():
            if total_revenue > 0:
                tour_revenue_account = qb_mappings["tour_revenue"].get(tour_name, {}).get("account", f"Tour Revenue - {tour_name}")
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': tour_revenue_account,
                    'Description': f'{tour_name} revenue - payments',
                    'Debit': '',
                    'Credit': f'{total_revenue:.2f}',
                    'Memo': f'Direct tour revenue for {tour_name} - payments (ex-VAT)'
                })

        # 2. Direct Tour Revenue - REFUNDS (Debits)
        direct_refunds = direct_bookings[direct_bookings['Payment or Refund'] == 'Refund']
        refund_revenue_by_tour = {}
        
        for _, row in direct_refunds.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            # Calculate fees for this refund booking
            tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name] if not fee_mappings_df.empty else pd.DataFrame()
            booking_fee_amount = 0
            
            if not tour_fees.empty:
                for _, fee_row in tour_fees.iterrows():
                    fee_amount = fee_row['per_person_amount'] * guests
                    booking_fee_amount += fee_amount
            
            # Tour revenue refund for this booking = Subtotal Paid + Fees (since subtotal_paid is already negative)
            # We add fees back because both tour revenue and fee revenue need to be reversed
            booking_tour_refund = subtotal_paid + booking_fee_amount
            
            if booking_tour_refund < 0:  # Should be negative for refunds
                if tour_name in refund_revenue_by_tour:
                    refund_revenue_by_tour[tour_name] += booking_tour_refund
                else:
                    refund_revenue_by_tour[tour_name] = booking_tour_refund
        
        # Create refund revenue entries (debits)
        for tour_name, total_refund in refund_revenue_by_tour.items():
            if total_refund < 0:  # Confirm it's a refund
                tour_revenue_account = qb_mappings["tour_revenue"].get(tour_name, {}).get("account", f"Tour Revenue - {tour_name}")
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': tour_revenue_account,
                    'Description': f'{tour_name} revenue - refunds',
                    'Debit': f'{abs(total_refund):.2f}',  # Make positive for debit
                    'Credit': '',
                    'Memo': f'Direct tour revenue refund for {tour_name} - refunds (ex-VAT)'
                })

        # 2. Affiliate revenue is handled through commission expense entries below
        # No separate affiliate revenue entries needed

        # 3. Fee Revenue - PAYMENTS (Credits) and REFUNDS (Debits) - Split separately
        # Calculate fee revenue from payments (positive)
        fee_revenue_payments = {}
        for _, row in direct_payments.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            if not fee_mappings_df.empty and guests > 0:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                for _, fee_row in tour_fees.iterrows():
                    fee_amount = fee_row['per_person_amount'] * guests
                    if fee_amount > 0:
                        fee_name = fee_row['fee_name']
                        if fee_name in fee_revenue_payments:
                            fee_revenue_payments[fee_name] += fee_amount
                        else:
                            fee_revenue_payments[fee_name] = fee_amount
        
        # Create fee revenue entries for payments (credits)
        for fee_name, fee_amount in fee_revenue_payments.items():
            if fee_amount > 0:
                fee_revenue_account = qb_mappings['fee_revenue'].get(fee_name, {}).get('account', f'Fee Revenue - {fee_name}')
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': fee_revenue_account,
                    'Description': f'{fee_name} revenue - payments',
                    'Debit': '',
                    'Credit': f'{fee_amount:.2f}',
                    'Memo': f'{fee_name} revenue from payments (all tours, ex-VAT)'
                })
        
        # Calculate fee revenue from refunds (negative - create debits)
        fee_revenue_refunds = {}
        for _, row in direct_refunds.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            if not fee_mappings_df.empty and guests > 0:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                for _, fee_row in tour_fees.iterrows():
                    fee_amount = fee_row['per_person_amount'] * guests
                    if fee_amount > 0:
                        fee_name = fee_row['fee_name']
                        if fee_name in fee_revenue_refunds:
                            fee_revenue_refunds[fee_name] += fee_amount
                        else:
                            fee_revenue_refunds[fee_name] = fee_amount
        
        # Create fee revenue entries for refunds (debits)
        for fee_name, fee_amount in fee_revenue_refunds.items():
            if fee_amount > 0:
                fee_revenue_account = qb_mappings['fee_revenue'].get(fee_name, {}).get('account', f'Fee Revenue - {fee_name}')
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': fee_revenue_account,
                    'Description': f'{fee_name} revenue - refunds',
                    'Debit': f'{fee_amount:.2f}',
                    'Credit': '',
                    'Memo': f'{fee_name} revenue refund (all tours, ex-VAT)'
                })

        # 4. Affiliate Commission Expense (debits) and Payables/Receivables
        for affiliate_name, commission_amount in affiliate_commissions.items():
            if commission_amount > 0:
                # Debit: Commission Expense
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': 'Affiliate Commission Expense',
                    'Description': f'{affiliate_name} commission expense',
                    'Debit': f'{commission_amount:.2f}',
                    'Credit': '',
                    'Memo': f'Commission expense to {affiliate_name}'
                })

                # Credit: Affiliate Payable or Debit: Affiliate Receivable
                if affiliate_name in affiliate_payables and affiliate_payables[affiliate_name] > 0:
                    # We owe commission to affiliate (we collected payment)
                    journal_entries.append({
                        'Entry Number': je_number,
                        'Date': entry_date,
                        'Account': f'Accounts Payable - {affiliate_name}',
                        'Description': f'{affiliate_name} commission payable',
                        'Debit': '',
                        'Credit': f'{affiliate_payables[affiliate_name]:.2f}',
                        'Memo': f'Commission payable to {affiliate_name}'
                    })
                elif affiliate_name in affiliate_receivables and affiliate_receivables[affiliate_name] > 0:
                    # Affiliate owes us (they collected payment)
                    journal_entries.append({
                        'Entry Number': je_number,
                        'Date': entry_date,
                        'Account': f'Accounts Receivable - {affiliate_name}',
                        'Description': f'{affiliate_name} commission receivable',
                        'Debit': f'{affiliate_receivables[affiliate_name]:.2f}',
                        'Credit': '',
                        'Memo': f'Commission receivable from {affiliate_name}'
                    })

        # 5. VAT Credits - separate payments and refunds
        # Get the sales VAT liability account from mappings
        sales_vat_account = qb_mappings.get('sales_vat_liability', {}).get('Sales VAT', {}).get('account', 'Sales Tax Payable')
        
        if total_vat_payments > 0:
            journal_entries.append({
                'Entry Number': je_number,
                'Date': entry_date,
                'Account': sales_vat_account,
                'Description': 'VAT on direct payments',
                'Debit': '',
                'Credit': f'{total_vat_payments:.2f}',
                'Memo': f'VAT collected on direct payments (${total_vat_payments:.2f})'
            })

        # Add VAT refund entry if there are refunds
        if total_vat_refunds > 0:
            journal_entries.append({
                'Entry Number': je_number,
                'Date': entry_date,
                'Account': sales_vat_account,
                'Description': 'VAT on refunds',
                'Debit': f'{total_vat_refunds:.2f}',
                'Credit': '',
                'Memo': f'VAT refunded on direct refunds (${total_vat_refunds:.2f})'
            })

        # 6. Processing Fee Expenses (if enabled) - V1
        if include_processing_fees:
            for payment_type, total_processing_fee in total_processing_fees_by_type.items():
                if total_processing_fee != 0:
                    # Get the payment account for this payment type
                    payment_account = qb_mappings['payment_type'].get(payment_type, {}).get('account', get_payment_account(payment_type))
                    
                    # Get the processing fee expense account from mappings (single account for all payment types)
                    processing_fee_account = qb_mappings.get('processing_fee_expense', {}).get('Processing Fees', {}).get('account', 'Processing Fee Expense')
                    
                    # Processing fees: 
                    # - For payments (negative): Debit expense, Credit payment clearing
                    # - For refunds (positive): Credit expense, Debit payment clearing
                    
                    if total_processing_fee < 0:
                        # Payment processing fees (negative) - expense to us
                        # 1. Debit: Processing Fee Expense
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': processing_fee_account,
                            'Description': f'{payment_type} processing fee expense (V1)',
                            'Debit': f'{abs(total_processing_fee):.2f}',
                            'Credit': '',
                            'Memo': f'V1: Processing fees for {payment_type} payments'
                        })
                        
                        # 2. Credit: Reduce Payment Clearing Account
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': payment_account,
                            'Description': f'{payment_type} processing fee adjustment (V1)',
                            'Debit': '',
                            'Credit': f'{abs(total_processing_fee):.2f}',
                            'Memo': f'V1: Processing fee reduction for {payment_type} clearing'
                        })
                    else:
                        # Refund processing fees (positive) - refund to us
                        # 1. Credit: Reduce Processing Fee Expense
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': processing_fee_account,
                            'Description': f'{payment_type} processing fee refund (V1)',
                            'Debit': '',
                            'Credit': f'{total_processing_fee:.2f}',
                            'Memo': f'V1: Processing fee refunds for {payment_type} refunds'
                        })
                        
                        # 2. Debit: Increase Payment Clearing Account
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': payment_account,
                            'Description': f'{payment_type} processing fee refund adjustment (V1)',
                            'Debit': f'{total_processing_fee:.2f}',
                            'Credit': '',
                            'Memo': f'V1: Processing fee refund increase for {payment_type} clearing'
                        })

        # PAYMENT SIDE (Debits) - All payments in one entry

        # 1. Direct booking payments
        for payment_type, total_amount in total_payments_by_type.items():
            if total_amount > 0:
                payment_account = qb_mappings['payment_type'].get(payment_type, {}).get('account', get_payment_account(payment_type))

                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': payment_account,
                    'Description': f'{payment_type} payment',
                    'Debit': f'{total_amount:.2f}',
                    'Credit': '',
                    'Memo': f'Direct booking payment via {payment_type}'
                })

        # 2. Affiliate payment receipts (from affiliate payments collected)
        for affiliate_payment_type, payment_amount in affiliate_payments_by_type.items():
            if payment_amount > 0:
                # Extract affiliate name from payment type
                if 'Affiliate Payment - ' in affiliate_payment_type:
                    affiliate_name = affiliate_payment_type.replace('Affiliate Payment - ', '')

                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': f'Accounts Receivable - {affiliate_name}',
                    'Description': f'{affiliate_name} payment received',
                    'Debit': f'{payment_amount:.2f}',
                    'Credit': '',
                    'Memo': f'Payment received from affiliate {affiliate_name}'
                })

        # Note: Refunds are already accounted for in Net Revenue Collected
        # No separate refund entries needed

                entry_number += 1

        # 7. Balance Check and Rounding Adjustment (V1)
        if journal_entries:
            # Calculate total debits and credits
            total_debits = 0
            total_credits = 0
            
            for entry in journal_entries:
                debit_str = entry.get('Debit', '')
                credit_str = entry.get('Credit', '')
                
                if debit_str and debit_str != '':
                    total_debits += float(debit_str)
                if credit_str and credit_str != '':
                    total_credits += float(credit_str)
            
            # Check if there's an imbalance
            difference = total_debits - total_credits
            
            if abs(difference) > 0.01 and abs(difference) <= 5.00:
                # Add rounding adjustment entry
                if difference > 0:
                    # More debits than credits - need a credit to balance
                    journal_entries.append({
                        'Entry Number': je_number,
                        'Date': entry_date,
                        'Account': 'Rounding Difference',
                        'Description': 'Rounding adjustment (V1)',
                        'Debit': '',
                        'Credit': f'{abs(difference):.2f}',
                        'Memo': f'V1: Rounding adjustment to balance journal entry (${abs(difference):.2f})'
                    })
                else:
                    # More credits than debits - need a debit to balance
                    journal_entries.append({
                        'Entry Number': je_number,
                        'Date': entry_date,
                        'Account': 'Rounding Difference',
                        'Description': 'Rounding adjustment (V1)',
                        'Debit': f'{abs(difference):.2f}',
                        'Credit': '',
                        'Memo': f'V1: Rounding adjustment to balance journal entry (${abs(difference):.2f})'
                    })
            elif abs(difference) > 5.00:
                # Large imbalance - log warning but don't auto-adjust
                st.warning(f"⚠️ V1 Journal imbalance detected: ${difference:.2f} (Debits: ${total_debits:.2f}, Credits: ${total_credits:.2f}). Manual review recommended.")

        # Calculate net payment totals (gross payments minus processing fees)
        net_payments_by_type = {}
        for payment_type, gross_amount in total_payments_by_type.items():
            processing_fee = total_processing_fees_by_type.get(payment_type, 0)
            # Processing fees are negative for payments (expenses), so we add them to reduce the gross
            net_amount = gross_amount + processing_fee  # processing_fee is negative, so this reduces gross
            net_payments_by_type[payment_type] = net_amount

        # Convert to DataFrame
        if journal_entries:
            journal_df = pd.DataFrame(journal_entries)

            # Note: V1 journal is for display/CSV export only
            # Only save to database if this is the final version being sent to QuickBooks

            return journal_df, total_vat_payments, total_vat_refunds, total_payments_by_type, total_processing_fees_by_type, net_payments_by_type
        else:
            return pd.DataFrame(), 0, 0, {}, {}, {}

    except Exception as e:
        st.error(f"❌ Error creating enhanced QuickBooks journal: {str(e)}")
        import traceback
        st.error(f"Details: {traceback.format_exc()}")
        return pd.DataFrame(), 0, 0, {}, {}, {}


def calculate_proportional_fees_v2(subtotal_paid, subtotal_total, total_fees_for_booking):
    """
    Calculate proportional fees based on partial payment
    Formula: (Subtotal Paid / Subtotal Total) * Total Fees
    
    Special cases:
    - If subtotal_total is 0, return 0
    - If payment >= subtotal (overpayment), cap proportion at 1.0 (100% of fees)
    """
    if subtotal_total == 0:
        return 0
    
    proportion = abs(subtotal_paid) / subtotal_total  # Use abs for refunds
    
    # Cap proportion at 1.0 for overpayment scenarios
    # This prevents fees from being more than 100% of the total booking fees
    proportion = min(proportion, 1.0)
    
    return proportion * total_fees_for_booking


def create_enhanced_quickbooks_journal_api_v2(pivot_df, raw_df, include_processing_fees=False):
    """Create V2 QuickBooks API-compatible JournalEntry objects (JSON format for API integration) - excludes affiliate payments received"""
    try:
        journal_entries = []
        entry_date = datetime.now().strftime('%Y-%m-%d')

        # Retrieve QuickBooks account mappings
        qb_mappings = get_quickbooks_mappings()

        # Get fee mappings for detailed breakdown
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

        entry_number = 1
        total_vat_amount = 0

        # V2: All data passed in is already filtered to exclude affiliate payments received
        # Use all remaining bookings (no need to separate by Affiliate column since V2 filter handles this)
        direct_bookings = raw_df.copy()

        # Separate payments and refunds
        payments_df = raw_df[raw_df['Payment or Refund'] == 'Payment'].copy()
        refunds_df = raw_df[raw_df['Payment or Refund'] == 'Refund'].copy()

        # Calculate total VAT from direct bookings - separate payments and refunds
        payments_only_df = direct_bookings[direct_bookings['Payment or Refund'] == 'Payment']
        refunds_only_df = direct_bookings[direct_bookings['Payment or Refund'] == 'Refund']

        total_vat_payments = 0
        total_vat_refunds = 0

        if not payments_only_df.empty and 'Tax Paid' in payments_only_df.columns:
            total_vat_payments = pd.to_numeric(payments_only_df['Tax Paid'], errors='coerce').fillna(0).sum()

        if not refunds_only_df.empty and 'Tax Paid' in refunds_only_df.columns:
            # Refunds are negative, so we take absolute value for VAT refunds
            total_vat_refunds = abs(pd.to_numeric(refunds_only_df['Tax Paid'], errors='coerce').fillna(0).sum())

        total_vat_amount = total_vat_payments  # Only use payment VAT for journal entry

        # V2 filtering already excludes affiliate payments, so no separate affiliate processing needed

        # Calculate total payments by payment type from ALL bookings (V2 filtered)
        total_payments_by_type = {}
        total_processing_fees_by_type = {}  # Track processing fees separately

        # Process all V2-filtered bookings payments
        for _, row in pivot_df.iterrows():
            tour_name = row['Tour Name']
            # Use all V2-filtered booking transactions for payments
            tour_transactions = direct_bookings[direct_bookings['Item'] == tour_name].copy()

            if not tour_transactions.empty:
                # Calculate payment breakdown using Subtotal Paid + Tax Paid
                tour_payment_breakdown = {}
                tour_processing_fee_breakdown = {}

                for _, transaction in tour_transactions.iterrows():
                    payment_type = transaction.get('Payment Type', 'Unknown')
                    subtotal_paid = pd.to_numeric(transaction.get('Subtotal Paid', 0), errors='coerce')
                    tax_paid = pd.to_numeric(transaction.get('Tax Paid', 0), errors='coerce')
                    processing_fee = pd.to_numeric(transaction.get('Processing Fee', 0), errors='coerce')

                    # Base payment amount (always use gross amount for clearing accounts)
                    base_payment = subtotal_paid + tax_paid

                    # Always use gross payment amount for clearing accounts
                    # Processing fees will be handled as separate credit entries

                    # Aggregate payment amounts (gross)
                    if payment_type in tour_payment_breakdown:
                        tour_payment_breakdown[payment_type] += base_payment
                    else:
                        tour_payment_breakdown[payment_type] = base_payment

                    # Aggregate processing fees if enabled
                    if include_processing_fees and processing_fee != 0:
                        if payment_type in tour_processing_fee_breakdown:
                            tour_processing_fee_breakdown[payment_type] += processing_fee
                        else:
                            tour_processing_fee_breakdown[payment_type] = processing_fee

                # Add to overall totals
                for payment_type, amount in tour_payment_breakdown.items():
                    if payment_type in total_payments_by_type:
                        total_payments_by_type[payment_type] += amount
                    else:
                        total_payments_by_type[payment_type] = amount

                # Add processing fees to overall totals
                for payment_type, fee_amount in tour_processing_fee_breakdown.items():
                    if payment_type in total_processing_fees_by_type:
                        total_processing_fees_by_type[payment_type] += fee_amount
                    else:
                        total_processing_fees_by_type[payment_type] = fee_amount

        # No separate affiliate payment processing needed - V2 filter excludes these

        # Create ONE consolidated journal entry (V2)
        je_number = f'JE{entry_number:04d}'

        # Generate journal code using date and time (max 21 chars for QuickBooks)
        journal_code = datetime.now().strftime('%y%m%d%H%M%S-API_V2')

        # Initialize API-compliant journal entry structure with the date-time journal code
        api_journal_entry = {
            "DocNumber": journal_code,  # Use date-time based journal code
            "TxnDate": entry_date,
            "Adjustment": False,
            "Line": []
        }

        line_num = 1

        # Fee calculation is now done separately for payments and refunds below - V2

        # Define direct payments and refunds for fee calculation
        direct_payments = direct_bookings[direct_bookings['Payment or Refund'] == 'Payment']
        direct_refunds = direct_bookings[direct_bookings['Payment or Refund'] == 'Refund']

        # REVENUE SIDE (Credits) - Generate directly from CSV records, not pivot tables

        # 1. Tour Revenue - PAYMENTS (Credits) - V2 Filtered
        payment_revenue_by_tour = {}

        for _, row in direct_payments.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')

            # Calculate total fees for this booking (full booking)
            total_fees_for_booking = 0
            if not fee_mappings_df.empty:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests

            # Calculate proportional fees based on payment amount
            proportional_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))

            # Tour revenue for this booking = Subtotal Paid - Proportional Fees
            booking_tour_revenue = subtotal_paid - proportional_fees

            if booking_tour_revenue > 0:
                if tour_name in payment_revenue_by_tour:
                    payment_revenue_by_tour[tour_name] += booking_tour_revenue
                else:
                    payment_revenue_by_tour[tour_name] = booking_tour_revenue

        # Create payment revenue entries
        for tour_name, total_revenue in payment_revenue_by_tour.items():
            if total_revenue > 0:
                tour_revenue_mapping = qb_mappings["tour_revenue"].get(tour_name, {})
                account_id = tour_revenue_mapping.get("account_id", "")
                account_name = tour_revenue_mapping.get("account", f"Tour Revenue - {tour_name}")

                if account_id:  # Only create entry if we have an account ID
                    api_journal_entry["Line"].append({
                        "DetailType": "JournalEntryLineDetail",
                        "JournalEntryLineDetail": {
                            "PostingType": "Credit",
                            "AccountRef": {
                                "value": account_id,
                                "name": account_name
                            }
                        },
                        "Amount": round(float(total_revenue), 2),
                        "Description": f'{tour_name} revenue - payments (V2)',
                        "LineNum": line_num
                    })
                    line_num += 1

        # 2. Tour Revenue - REFUNDS (Debits) - V2 Filtered
        refund_revenue_by_tour = {}

        for _, row in direct_refunds.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')

            # Calculate total fees for this booking (full booking)
            total_fees_for_booking = 0
            if not fee_mappings_df.empty:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests

            # Calculate proportional fees based on refund amount
            proportional_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))

            # Tour revenue refund for this booking = Subtotal Paid + Proportional Fees (since subtotal_paid is already negative)
            # We add proportional fees back because both tour revenue and fee revenue need to be reversed proportionally
            booking_tour_refund = subtotal_paid + proportional_fees

            if booking_tour_refund < 0:  # Should be negative for refunds
                if tour_name in refund_revenue_by_tour:
                    refund_revenue_by_tour[tour_name] += booking_tour_refund
                else:
                    refund_revenue_by_tour[tour_name] = booking_tour_refund

        # Create refund revenue entries (debits)
        for tour_name, total_refund in refund_revenue_by_tour.items():
            if total_refund < 0:  # Confirm it's a refund
                tour_revenue_mapping = qb_mappings["tour_revenue"].get(tour_name, {})
                account_id = tour_revenue_mapping.get("account_id", "")
                account_name = tour_revenue_mapping.get("account", f"Tour Revenue - {tour_name}")

                if account_id:  # Only create entry if we have an account ID
                    api_journal_entry["Line"].append({
                        "DetailType": "JournalEntryLineDetail",
                        "JournalEntryLineDetail": {
                            "PostingType": "Debit",
                            "AccountRef": {
                                "value": account_id,
                                "name": account_name
                            }
                        },
                        "Amount": round(abs(float(total_refund)), 2),  # Make positive for debit
                        "Description": f'{tour_name} revenue - refunds (V2)',
                        "LineNum": line_num
                    })
                    line_num += 1

        # 2. Affiliate revenue is handled through commission expense entries below
        # No separate affiliate revenue entries needed

        # 3. Fee Revenue - PAYMENTS (Credits) and REFUNDS (Debits) - Split separately - V2
        # Calculate fee revenue from payments (positive) - using proportional fees
        fee_revenue_payments = {}
        for _, row in direct_payments.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')

            if not fee_mappings_df.empty and guests > 0:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]

                # Calculate total fees for this booking (full booking)
                total_fees_for_booking = 0
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests

                # Calculate proportional fees
                proportional_total_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))

                # Distribute proportional fees across individual fee types
                if total_fees_for_booking > 0:
                    for _, fee_row in tour_fees.iterrows():
                        full_fee_amount = fee_row['per_person_amount'] * guests
                        fee_proportion = full_fee_amount / total_fees_for_booking
                        proportional_fee_amount = proportional_total_fees * fee_proportion

                        if proportional_fee_amount > 0:
                            fee_name = fee_row['fee_name']
                            if fee_name in fee_revenue_payments:
                                fee_revenue_payments[fee_name] += proportional_fee_amount
                            else:
                                fee_revenue_payments[fee_name] = proportional_fee_amount

        # Create fee revenue entries for payments (credits)
        for fee_name, fee_amount in fee_revenue_payments.items():
            if fee_amount > 0:
                fee_revenue_mapping = qb_mappings['fee_revenue'].get(fee_name, {})
                account_id = fee_revenue_mapping.get('account_id', "")
                account_name = fee_revenue_mapping.get('account', f'Fee Revenue - {fee_name}')

                if account_id:  # Only create entry if we have an account ID
                    api_journal_entry["Line"].append({
                        "DetailType": "JournalEntryLineDetail",
                        "JournalEntryLineDetail": {
                            "PostingType": "Credit",
                            "AccountRef": {
                                "value": account_id,
                                "name": account_name
                            }
                        },
                        "Amount": round(float(fee_amount), 2),
                        "Description": f'{fee_name} revenue - payments (V2)',
                        "LineNum": line_num
                    })
                    line_num += 1

        # Calculate fee revenue from refunds (negative - create debits) - using proportional fees
        fee_revenue_refunds = {}
        for _, row in direct_refunds.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')

            if not fee_mappings_df.empty and guests > 0:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]

                # Calculate total fees for this booking (full booking)
                total_fees_for_booking = 0
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests

                # Calculate proportional fees (using absolute value for refunds)
                proportional_total_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))

                # Distribute proportional fees across individual fee types
                if total_fees_for_booking > 0:
                    for _, fee_row in tour_fees.iterrows():
                        full_fee_amount = fee_row['per_person_amount'] * guests
                        fee_proportion = full_fee_amount / total_fees_for_booking
                        proportional_fee_amount = proportional_total_fees * fee_proportion

                        if proportional_fee_amount > 0:
                            fee_name = fee_row['fee_name']
                            if fee_name in fee_revenue_refunds:
                                fee_revenue_refunds[fee_name] += proportional_fee_amount
                            else:
                                fee_revenue_refunds[fee_name] = proportional_fee_amount

        # Create fee revenue entries for refunds (debits)
        for fee_name, fee_amount in fee_revenue_refunds.items():
            if fee_amount > 0:
                fee_revenue_mapping = qb_mappings['fee_revenue'].get(fee_name, {})
                account_id = fee_revenue_mapping.get('account_id', "")
                account_name = fee_revenue_mapping.get('account', f'Fee Revenue - {fee_name}')

                if account_id:  # Only create entry if we have an account ID
                    api_journal_entry["Line"].append({
                        "DetailType": "JournalEntryLineDetail",
                        "JournalEntryLineDetail": {
                            "PostingType": "Debit",
                            "AccountRef": {
                                "value": account_id,
                                "name": account_name
                            }
                        },
                        "Amount": round(float(fee_amount), 2),
                        "Description": f'{fee_name} revenue - refunds (V2)',
                        "LineNum": line_num
                    })
                    line_num += 1

        # 4. No affiliate commission processing needed - V2 filter excludes these

        # 5. VAT Credits - separate payments and refunds - V2
        # Get the sales VAT liability account from mappings
        sales_vat_mapping = qb_mappings.get('sales_vat_liability', {}).get('Sales VAT', {})
        sales_vat_account_id = sales_vat_mapping.get('account_id', "")
        sales_vat_account_name = sales_vat_mapping.get('account', 'Sales Tax Payable')

        if total_vat_payments > 0 and sales_vat_account_id:
            api_journal_entry["Line"].append({
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Credit",
                    "AccountRef": {
                        "value": sales_vat_account_id,
                        "name": sales_vat_account_name
                    }
                },
                "Amount": round(float(total_vat_payments), 2),
                "Description": 'VAT on direct payments (V2)',
                "LineNum": line_num
            })
            line_num += 1

        # Add VAT refund entry if there are refunds
        if total_vat_refunds > 0 and sales_vat_account_id:
            api_journal_entry["Line"].append({
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Debit",
                    "AccountRef": {
                        "value": sales_vat_account_id,
                        "name": sales_vat_account_name
                    }
                },
                "Amount": round(float(total_vat_refunds), 2),
                "Description": 'VAT on refunds (V2)',
                "LineNum": line_num
            })
            line_num += 1

        # 6. Processing Fee Expenses (if enabled) - V2
        if include_processing_fees:
            for payment_type, total_processing_fee in total_processing_fees_by_type.items():
                if total_processing_fee != 0:
                    # Get the payment account for this payment type
                    payment_mapping = qb_mappings['payment_type'].get(payment_type, {})
                    payment_account_id = payment_mapping.get('account_id', "")
                    payment_account_name = payment_mapping.get('account', get_payment_account(payment_type))

                    # Get the processing fee expense account from mappings (single account for all payment types)
                    processing_fee_mapping = qb_mappings.get('processing_fee_expense', {}).get('Processing Fees', {})
                    processing_fee_account_id = processing_fee_mapping.get('account_id', "")
                    processing_fee_account_name = processing_fee_mapping.get('account', 'Processing Fee Expense')

                    if total_processing_fee < 0 and payment_account_id and processing_fee_account_id:
                        # Payment processing fees (negative) - expense to us
                        # 1. Debit: Processing Fee Expense
                        api_journal_entry["Line"].append({
                            "DetailType": "JournalEntryLineDetail",
                            "JournalEntryLineDetail": {
                                "PostingType": "Debit",
                                "AccountRef": {
                                    "value": processing_fee_account_id,
                                    "name": processing_fee_account_name
                                }
                            },
                            "Amount": round(abs(float(total_processing_fee)), 2),
                            "Description": f'{payment_type} processing fee expense (V2)',
                            "LineNum": line_num
                        })
                        line_num += 1

                        # 2. Credit: Reduce Payment Clearing Account
                        api_journal_entry["Line"].append({
                            "DetailType": "JournalEntryLineDetail",
                            "JournalEntryLineDetail": {
                                "PostingType": "Credit",
                                "AccountRef": {
                                    "value": payment_account_id,
                                    "name": payment_account_name
                                }
                            },
                            "Amount": round(abs(float(total_processing_fee)), 2),
                            "Description": f'{payment_type} processing fee adjustment (V2)',
                            "LineNum": line_num
                        })
                        line_num += 1
                    elif total_processing_fee > 0 and payment_account_id and processing_fee_account_id:
                        # Refund processing fees (positive) - refund to us
                        # 1. Credit: Reduce Processing Fee Expense
                        api_journal_entry["Line"].append({
                            "DetailType": "JournalEntryLineDetail",
                            "JournalEntryLineDetail": {
                                "PostingType": "Credit",
                                "AccountRef": {
                                    "value": processing_fee_account_id,
                                    "name": processing_fee_account_name
                                }
                            },
                            "Amount": round(float(total_processing_fee), 2),
                            "Description": f'{payment_type} processing fee refund (V2)',
                            "LineNum": line_num
                        })
                        line_num += 1

                        # 2. Debit: Increase Payment Clearing Account
                        api_journal_entry["Line"].append({
                            "DetailType": "JournalEntryLineDetail",
                            "JournalEntryLineDetail": {
                                "PostingType": "Debit",
                                "AccountRef": {
                                    "value": payment_account_id,
                                    "name": payment_account_name
                                }
                            },
                            "Amount": round(float(total_processing_fee), 2),
                            "Description": f'{payment_type} processing fee refund adjustment (V2)',
                            "LineNum": line_num
                        })
                        line_num += 1

        # PAYMENT SIDE (Debits) - All payments in one entry (V2)

        # 1. Direct booking payments
        for payment_type, total_amount in total_payments_by_type.items():
            if total_amount > 0:
                payment_mapping = qb_mappings['payment_type'].get(payment_type, {})
                payment_account_id = payment_mapping.get('account_id', "")
                payment_account_name = payment_mapping.get('account', get_payment_account(payment_type))

                if payment_account_id:  # Only create entry if we have an account ID
                    api_journal_entry["Line"].append({
                        "DetailType": "JournalEntryLineDetail",
                        "JournalEntryLineDetail": {
                            "PostingType": "Debit",
                            "AccountRef": {
                                "value": payment_account_id,
                                "name": payment_account_name
                            }
                        },
                        "Amount": round(float(total_amount), 2),
                        "Description": f'{payment_type} payment (V2)',
                        "LineNum": line_num
                    })
                    line_num += 1

        # 2. No affiliate payment receipts processing needed - V2 filter excludes these

        # Balance Check and Smart Rounding Adjustment (API V2)
        rounding_adjustment_info = ""

        if api_journal_entry["Line"]:
            # Calculate total debits and credits
            total_debits = 0
            total_credits = 0

            for line in api_journal_entry["Line"]:
                amount = float(line["Amount"])
                posting_type = line["JournalEntryLineDetail"]["PostingType"]

                if posting_type == "Debit":
                    total_debits += amount
                elif posting_type == "Credit":
                    total_credits += amount

            # Check if there's an imbalance
            difference = total_debits - total_credits

            if abs(difference) > 0.01 and abs(difference) <= 0.05:
                # Smart rounding adjustment - modify existing account instead of creating new line
                # Priority order: 1) Cash clearing accounts, 2) Credit card clearing, 3) First payment account

                adjustment_applied = False
                adjusted_account = ""

                # Find the best account to adjust (prefer cash/clearing accounts)
                preferred_accounts = ['Cash - Operating', 'Credit Card Clearing', 'PayPal Clearing', 'Bank Transfer Clearing']

                # First try to find a preferred clearing account
                for line in api_journal_entry["Line"]:
                    account_name = line["JournalEntryLineDetail"]["AccountRef"]["name"]
                    posting_type = line["JournalEntryLineDetail"]["PostingType"]

                    if any(pref_acc in account_name for pref_acc in preferred_accounts):
                        current_amount = float(line["Amount"])

                        if difference > 0:
                            # More debits than credits - need to reduce a debit or increase a credit
                            if posting_type == "Debit" and current_amount >= abs(difference):
                                # Reduce the debit amount
                                line["Amount"] = round(current_amount - abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = account_name
                                break
                            elif posting_type == "Credit":
                                # Increase the credit amount
                                line["Amount"] = round(current_amount + abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = account_name
                                break
                        else:
                            # More credits than debits - need to reduce a credit or increase a debit
                            if posting_type == "Credit" and current_amount >= abs(difference):
                                # Reduce the credit amount
                                line["Amount"] = round(current_amount - abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = account_name
                                break
                            elif posting_type == "Debit":
                                # Increase the debit amount
                                line["Amount"] = round(current_amount + abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = account_name
                                break

                # If no preferred account found, use the first suitable payment account
                if not adjustment_applied:
                    for line in api_journal_entry["Line"]:
                        posting_type = line["JournalEntryLineDetail"]["PostingType"]
                        current_amount = float(line["Amount"])

                        if difference > 0:
                            # More debits than credits - need to reduce a debit or increase a credit
                            if posting_type == "Debit" and current_amount >= abs(difference):
                                line["Amount"] = round(current_amount - abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = line["JournalEntryLineDetail"]["AccountRef"]["name"]
                                break
                            elif posting_type == "Credit":
                                line["Amount"] = round(current_amount + abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = line["JournalEntryLineDetail"]["AccountRef"]["name"]
                                break
                        else:
                            # More credits than debits - need to reduce a credit or increase a debit
                            if posting_type == "Credit" and current_amount >= abs(difference):
                                line["Amount"] = round(current_amount - abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = line["JournalEntryLineDetail"]["AccountRef"]["name"]
                                break
                            elif posting_type == "Debit":
                                line["Amount"] = round(current_amount + abs(difference), 2)
                                adjustment_applied = True
                                adjusted_account = line["JournalEntryLineDetail"]["AccountRef"]["name"]
                                break

                if adjustment_applied:
                    rounding_adjustment_info = f"✅ Applied smart rounding adjustment of ${abs(difference):.2f} to '{adjusted_account}' account"
                else:
                    rounding_adjustment_info = f"⚠️ Could not apply rounding adjustment of ${abs(difference):.2f} - no suitable account found"

            elif abs(difference) > 0.05:
                # Large imbalance - log warning but don't auto-adjust
                rounding_adjustment_info = f"⚠️ Large imbalance detected: ${difference:.2f} (Debits: ${total_debits:.2f}, Credits: ${total_credits:.2f})"

            journal_entries.append(api_journal_entry)

        # Calculate net payment totals (gross payments minus processing fees)
        net_payments_by_type = {}
        for payment_type, gross_amount in total_payments_by_type.items():
            processing_fee = total_processing_fees_by_type.get(payment_type, 0)
            # Processing fees are negative for payments (expenses), so we add them to reduce the gross
            net_amount = gross_amount + processing_fee  # processing_fee is negative, so this reduces gross
            net_payments_by_type[payment_type] = net_amount

        # Note: Not saving to database anymore - using date/time as unique ID

        # Return the API-compliant journal entries with rounding adjustment info
        return journal_entries, total_vat_payments, total_vat_refunds, total_payments_by_type, total_processing_fees_by_type, net_payments_by_type, rounding_adjustment_info

    except Exception as e:
        st.error(f"❌ Error creating V2 API-compliant QuickBooks journal: {str(e)}")
        import traceback
        st.error(f"Details: {traceback.format_exc()}")
        return [], 0, 0, {}, {}, {}


def create_enhanced_quickbooks_journal_v2(pivot_df, raw_df, include_processing_fees=False):
    """Create V2 QuickBooks journal entries - excludes affiliate bookings where payment already received"""
    try:
        journal_entries = []
        entry_date = datetime.now().strftime('%Y-%m-%d')

        # Retrieve QuickBooks account mappings
        qb_mappings = get_quickbooks_mappings()

        # Get fee mappings for detailed breakdown
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

        entry_number = 1
        total_vat_amount = 0

        # V2: All data passed in is already filtered to exclude affiliate payments received
        # Use all remaining bookings (no need to separate by Affiliate column since V2 filter handles this)
        direct_bookings = raw_df.copy()

        # Separate payments and refunds
        payments_df = raw_df[raw_df['Payment or Refund'] == 'Payment'].copy()
        refunds_df = raw_df[raw_df['Payment or Refund'] == 'Refund'].copy()

        # Calculate total VAT from direct bookings - separate payments and refunds
        payments_only_df = direct_bookings[direct_bookings['Payment or Refund'] == 'Payment']
        refunds_only_df = direct_bookings[direct_bookings['Payment or Refund'] == 'Refund']

        total_vat_payments = 0
        total_vat_refunds = 0

        if not payments_only_df.empty and 'Tax Paid' in payments_only_df.columns:
            total_vat_payments = pd.to_numeric(payments_only_df['Tax Paid'], errors='coerce').fillna(0).sum()

        if not refunds_only_df.empty and 'Tax Paid' in refunds_only_df.columns:
            # Refunds are negative, so we take absolute value for VAT refunds
            total_vat_refunds = abs(pd.to_numeric(refunds_only_df['Tax Paid'], errors='coerce').fillna(0).sum())

        total_vat_amount = total_vat_payments  # Only use payment VAT for journal entry

        # V2 filtering already excludes affiliate payments, so no separate affiliate processing needed

        # Calculate total payments by payment type from ALL bookings (V2 filtered)
        total_payments_by_type = {}
        total_processing_fees_by_type = {}  # Track processing fees separately

        # Process all V2-filtered bookings payments
        for _, row in pivot_df.iterrows():
            tour_name = row['Tour Name']
            # Use all V2-filtered booking transactions for payments
            tour_transactions = direct_bookings[direct_bookings['Item'] == tour_name].copy()

            if not tour_transactions.empty:
                # Calculate payment breakdown using Subtotal Paid + Tax Paid
                tour_payment_breakdown = {}
                tour_processing_fee_breakdown = {}
                
                for _, transaction in tour_transactions.iterrows():
                    payment_type = transaction.get('Payment Type', 'Unknown')
                    subtotal_paid = pd.to_numeric(transaction.get('Subtotal Paid', 0), errors='coerce')
                    tax_paid = pd.to_numeric(transaction.get('Tax Paid', 0), errors='coerce')
                    processing_fee = pd.to_numeric(transaction.get('Processing Fee', 0), errors='coerce')
                    
                    # Base payment amount (always use gross amount for clearing accounts)
                    base_payment = subtotal_paid + tax_paid

                    # Always use gross payment amount for clearing accounts
                    # Processing fees will be handled as separate credit entries
                    
                    # Aggregate payment amounts (gross)
                    if payment_type in tour_payment_breakdown:
                        tour_payment_breakdown[payment_type] += base_payment
                    else:
                        tour_payment_breakdown[payment_type] = base_payment
                    
                    # Aggregate processing fees if enabled
                    if include_processing_fees and processing_fee != 0:
                        if payment_type in tour_processing_fee_breakdown:
                            tour_processing_fee_breakdown[payment_type] += processing_fee
                        else:
                            tour_processing_fee_breakdown[payment_type] = processing_fee

                # Add to overall totals
                for payment_type, amount in tour_payment_breakdown.items():
                    if payment_type in total_payments_by_type:
                        total_payments_by_type[payment_type] += amount
                    else:
                        total_payments_by_type[payment_type] = amount
                
                # Add processing fees to overall totals
                for payment_type, fee_amount in tour_processing_fee_breakdown.items():
                    if payment_type in total_processing_fees_by_type:
                        total_processing_fees_by_type[payment_type] += fee_amount
                    else:
                        total_processing_fees_by_type[payment_type] = fee_amount

        # No separate affiliate payment processing needed - V2 filter handles this

        # Create ONE consolidated journal entry (V2)
        je_number = f'JE{entry_number:04d}'

        # Fee calculation is now done separately for payments and refunds below - V2
        
        # Define direct payments and refunds for fee calculation
        direct_payments = direct_bookings[direct_bookings['Payment or Refund'] == 'Payment']
        direct_refunds = direct_bookings[direct_bookings['Payment or Refund'] == 'Refund']

        # REVENUE SIDE (Credits) - Generate directly from CSV records, not pivot tables
        
        # 1. Tour Revenue - PAYMENTS (Credits) - V2 Filtered
        payment_revenue_by_tour = {}
        
        for _, row in direct_payments.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            # Calculate total fees for this booking (full booking)
            total_fees_for_booking = 0
            if not fee_mappings_df.empty:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests
            
            # Calculate proportional fees based on payment amount
            proportional_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))
            
            # Tour revenue for this booking = Subtotal Paid - Proportional Fees
            booking_tour_revenue = subtotal_paid - proportional_fees
            
            if booking_tour_revenue > 0:
                if tour_name in payment_revenue_by_tour:
                    payment_revenue_by_tour[tour_name] += booking_tour_revenue
                else:
                    payment_revenue_by_tour[tour_name] = booking_tour_revenue
        
        # Create payment revenue entries
        for tour_name, total_revenue in payment_revenue_by_tour.items():
            if total_revenue > 0:
                tour_revenue_account = qb_mappings["tour_revenue"].get(tour_name, {}).get("account", f"Tour Revenue - {tour_name}")
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': tour_revenue_account,
                    'Description': f'{tour_name} revenue - payments (V2)',
                    'Debit': '',
                    'Credit': f'{total_revenue:.2f}',
                    'Memo': f'V2: Direct tour revenue for {tour_name} - payments (ex-VAT, excludes affiliate payments received)'
                })

        # 2. Tour Revenue - REFUNDS (Debits) - V2 Filtered
        refund_revenue_by_tour = {}
        
        for _, row in direct_refunds.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            # Calculate total fees for this booking (full booking)
            total_fees_for_booking = 0
            if not fee_mappings_df.empty:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests
            
            # Calculate proportional fees based on refund amount
            proportional_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))
            
            # Tour revenue refund for this booking = Subtotal Paid + Proportional Fees (since subtotal_paid is already negative)
            # We add proportional fees back because both tour revenue and fee revenue need to be reversed proportionally
            booking_tour_refund = subtotal_paid + proportional_fees
            
            if booking_tour_refund < 0:  # Should be negative for refunds
                if tour_name in refund_revenue_by_tour:
                    refund_revenue_by_tour[tour_name] += booking_tour_refund
                else:
                    refund_revenue_by_tour[tour_name] = booking_tour_refund
        
        # Create refund revenue entries (debits)
        for tour_name, total_refund in refund_revenue_by_tour.items():
            if total_refund < 0:  # Confirm it's a refund
                tour_revenue_account = qb_mappings["tour_revenue"].get(tour_name, {}).get("account", f"Tour Revenue - {tour_name}")
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': tour_revenue_account,
                    'Description': f'{tour_name} revenue - refunds (V2)',
                    'Debit': f'{abs(total_refund):.2f}',  # Make positive for debit
                    'Credit': '',
                    'Memo': f'V2: Direct tour revenue refund for {tour_name} - refunds (ex-VAT, excludes affiliate payments received)'
                })

        # 2. Affiliate revenue is handled through commission expense entries below
        # No separate affiliate revenue entries needed

        # 3. Fee Revenue - PAYMENTS (Credits) and REFUNDS (Debits) - Split separately - V2
        # Calculate fee revenue from payments (positive) - using proportional fees
        fee_revenue_payments = {}
        for _, row in direct_payments.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            if not fee_mappings_df.empty and guests > 0:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                
                # Calculate total fees for this booking (full booking)
                total_fees_for_booking = 0
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests
                
                # Calculate proportional fees
                proportional_total_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))
                
                # Distribute proportional fees across individual fee types
                if total_fees_for_booking > 0:
                    for _, fee_row in tour_fees.iterrows():
                        full_fee_amount = fee_row['per_person_amount'] * guests
                        fee_proportion = full_fee_amount / total_fees_for_booking
                        proportional_fee_amount = proportional_total_fees * fee_proportion
                        
                        if proportional_fee_amount > 0:
                            fee_name = fee_row['fee_name']
                            if fee_name in fee_revenue_payments:
                                fee_revenue_payments[fee_name] += proportional_fee_amount
                            else:
                                fee_revenue_payments[fee_name] = proportional_fee_amount
        
        # Create fee revenue entries for payments (credits)
        for fee_name, fee_amount in fee_revenue_payments.items():
            if fee_amount > 0:
                fee_revenue_account = qb_mappings['fee_revenue'].get(fee_name, {}).get('account', f'Fee Revenue - {fee_name}')
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': fee_revenue_account,
                    'Description': f'{fee_name} revenue - payments (V2)',
                    'Debit': '',
                    'Credit': f'{fee_amount:.2f}',
                    'Memo': f'V2: {fee_name} revenue from payments (all tours, ex-VAT, excludes affiliate payments received)'
                })
        
        # Calculate fee revenue from refunds (negative - create debits) - using proportional fees
        fee_revenue_refunds = {}
        for _, row in direct_refunds.iterrows():
            tour_name = row.get('Item', 'Unknown Tour')
            subtotal_paid = pd.to_numeric(row.get('Subtotal Paid', 0), errors='coerce')
            subtotal_total = pd.to_numeric(row.get('Subtotal', 0), errors='coerce')
            guests = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')
            
            if not fee_mappings_df.empty and guests > 0:
                tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]
                
                # Calculate total fees for this booking (full booking)
                total_fees_for_booking = 0
                for _, fee_row in tour_fees.iterrows():
                    total_fees_for_booking += fee_row['per_person_amount'] * guests
                
                # Calculate proportional fees (using absolute value for refunds)
                proportional_total_fees = calculate_proportional_fees_v2(subtotal_paid, subtotal_total, float(total_fees_for_booking))
                
                # Distribute proportional fees across individual fee types
                if total_fees_for_booking > 0:
                    for _, fee_row in tour_fees.iterrows():
                        full_fee_amount = fee_row['per_person_amount'] * guests
                        fee_proportion = full_fee_amount / total_fees_for_booking
                        proportional_fee_amount = proportional_total_fees * fee_proportion
                        
                        if proportional_fee_amount > 0:
                            fee_name = fee_row['fee_name']
                            if fee_name in fee_revenue_refunds:
                                fee_revenue_refunds[fee_name] += proportional_fee_amount
                            else:
                                fee_revenue_refunds[fee_name] = proportional_fee_amount
        
        # Create fee revenue entries for refunds (debits)
        for fee_name, fee_amount in fee_revenue_refunds.items():
            if fee_amount > 0:
                fee_revenue_account = qb_mappings['fee_revenue'].get(fee_name, {}).get('account', f'Fee Revenue - {fee_name}')
                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': fee_revenue_account,
                    'Description': f'{fee_name} revenue - refunds (V2)',
                    'Debit': f'{fee_amount:.2f}',
                    'Credit': '',
                    'Memo': f'V2: {fee_name} revenue refund (all tours, ex-VAT, excludes affiliate payments received)'
                })

        # 4. No affiliate commission processing needed - V2 filter excludes these

        # 5. VAT Credits - separate payments and refunds - V2
        # Get the sales VAT liability account from mappings
        sales_vat_account = qb_mappings.get('sales_vat_liability', {}).get('Sales VAT', {}).get('account', 'Sales Tax Payable')
        
        if total_vat_payments > 0:
            journal_entries.append({
                'Entry Number': je_number,
                'Date': entry_date,
                'Account': sales_vat_account,
                'Description': 'VAT on direct payments (V2)',
                'Debit': '',
                'Credit': f'{total_vat_payments:.2f}',
                'Memo': f'V2: VAT collected on direct payments (${total_vat_payments:.2f})'
            })

        # Add VAT refund entry if there are refunds
        if total_vat_refunds > 0:
            journal_entries.append({
                'Entry Number': je_number,
                'Date': entry_date,
                'Account': sales_vat_account,
                'Description': 'VAT on refunds (V2)',
                'Debit': f'{total_vat_refunds:.2f}',
                'Credit': '',
                'Memo': f'V2: VAT refunded on direct refunds (${total_vat_refunds:.2f})'
            })

        # 6. Processing Fee Expenses (if enabled) - V2
        if include_processing_fees:
            for payment_type, total_processing_fee in total_processing_fees_by_type.items():
                if total_processing_fee != 0:
                    # Get the payment account for this payment type
                    payment_account = qb_mappings['payment_type'].get(payment_type, {}).get('account', get_payment_account(payment_type))
                    
                    # Get the processing fee expense account from mappings (single account for all payment types)
                    processing_fee_account = qb_mappings.get('processing_fee_expense', {}).get('Processing Fees', {}).get('account', 'Processing Fee Expense')
                    
                    # Processing fees: 
                    # - For payments (negative): Debit expense, Credit payment clearing
                    # - For refunds (positive): Credit expense, Debit payment clearing
                    
                    if total_processing_fee < 0:
                        # Payment processing fees (negative) - expense to us
                        # 1. Debit: Processing Fee Expense
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': processing_fee_account,
                            'Description': f'{payment_type} processing fee expense (V2)',
                            'Debit': f'{abs(total_processing_fee):.2f}',
                            'Credit': '',
                            'Memo': f'V2: Processing fees for {payment_type} payments'
                        })
                        
                        # 2. Credit: Reduce Payment Clearing Account
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': payment_account,
                            'Description': f'{payment_type} processing fee adjustment (V2)',
                            'Debit': '',
                            'Credit': f'{abs(total_processing_fee):.2f}',
                            'Memo': f'V2: Processing fee reduction for {payment_type} clearing'
                        })
                    else:
                        # Refund processing fees (positive) - refund to us
                        # 1. Credit: Reduce Processing Fee Expense
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': processing_fee_account,
                            'Description': f'{payment_type} processing fee refund (V2)',
                            'Debit': '',
                            'Credit': f'{total_processing_fee:.2f}',
                            'Memo': f'V2: Processing fee refunds for {payment_type} refunds'
                        })
                        
                        # 2. Debit: Increase Payment Clearing Account
                        journal_entries.append({
                            'Entry Number': je_number,
                            'Date': entry_date,
                            'Account': payment_account,
                            'Description': f'{payment_type} processing fee refund adjustment (V2)',
                            'Debit': f'{total_processing_fee:.2f}',
                            'Credit': '',
                            'Memo': f'V2: Processing fee refund increase for {payment_type} clearing'
                        })

        # PAYMENT SIDE (Debits) - All payments in one entry (V2)

        # 1. Direct booking payments
        for payment_type, total_amount in total_payments_by_type.items():
            if total_amount > 0:
                payment_account = qb_mappings['payment_type'].get(payment_type, {}).get('account', get_payment_account(payment_type))

                journal_entries.append({
                    'Entry Number': je_number,
                    'Date': entry_date,
                    'Account': payment_account,
                    'Description': f'{payment_type} payment (V2)',
                    'Debit': f'{total_amount:.2f}',
                    'Credit': '',
                    'Memo': f'V2: Direct booking payment via {payment_type} (excludes affiliate payments received)'
                })

        # 2. No affiliate payment receipts processing needed - V2 filter excludes these

        # 7. Balance Check and Rounding Adjustment (V2)
        if journal_entries:
            # Calculate total debits and credits
            total_debits = 0
            total_credits = 0
            
            for entry in journal_entries:
                debit_str = entry.get('Debit', '')
                credit_str = entry.get('Credit', '')
                
                if debit_str and debit_str != '':
                    total_debits += float(debit_str)
                if credit_str and credit_str != '':
                    total_credits += float(credit_str)
            
            # Check if there's an imbalance
            difference = total_debits - total_credits
            
            if abs(difference) > 0.01 and abs(difference) <= 5.00:
                # Add rounding adjustment entry
                if difference > 0:
                    # More debits than credits - need a credit to balance
                    journal_entries.append({
                        'Entry Number': je_number,
                        'Date': entry_date,
                        'Account': 'Rounding Difference',
                        'Description': 'Rounding adjustment (V2)',
                        'Debit': '',
                        'Credit': f'{abs(difference):.2f}',
                        'Memo': f'V2: Rounding adjustment to balance journal entry (${abs(difference):.2f})'
                    })
                else:
                    # More credits than debits - need a debit to balance
                    journal_entries.append({
                        'Entry Number': je_number,
                        'Date': entry_date,
                        'Account': 'Rounding Difference',
                        'Description': 'Rounding adjustment (V2)',
                        'Debit': f'{abs(difference):.2f}',
                        'Credit': '',
                        'Memo': f'V2: Rounding adjustment to balance journal entry (${abs(difference):.2f})'
                    })
            elif abs(difference) > 5.00:
                # Large imbalance - log warning but don't auto-adjust
                st.warning(f"⚠️ V2 Journal imbalance detected: ${difference:.2f} (Debits: ${total_debits:.2f}, Credits: ${total_credits:.2f}). Manual review recommended.")

        # Calculate net payment totals (gross payments minus processing fees)
        net_payments_by_type = {}
        for payment_type, gross_amount in total_payments_by_type.items():
            processing_fee = total_processing_fees_by_type.get(payment_type, 0)
            # Processing fees are negative for payments (expenses), so we add them to reduce the gross
            net_amount = gross_amount + processing_fee  # processing_fee is negative, so this reduces gross
            net_payments_by_type[payment_type] = net_amount

        # Convert to DataFrame
        if journal_entries:
            journal_df = pd.DataFrame(journal_entries)

            # Note: V2 journal is for display/CSV export only
            # The actual journal saving happens in the API_V2 version that gets sent to QuickBooks

            # Return both the journal and VAT totals
            return journal_df, total_vat_payments, total_vat_refunds, total_payments_by_type, total_processing_fees_by_type, net_payments_by_type
        else:
            return pd.DataFrame(), 0, 0, {}, {}, {}

    except Exception as e:
        st.error(f"❌ Error creating V2 QuickBooks journal: {str(e)}")
        import traceback
        st.error(f"Details: {traceback.format_exc()}")
        return pd.DataFrame(), 0, 0, {}, {}, {}


def create_v2_detailed_records(v2_filtered_df):
    """Create detailed records CSV for V2 journal calculations with fee breakdown"""
    try:
        # Create detailed records CSV for V2 journal calculations
        v2_detailed_records = v2_filtered_df.copy()

        # Select key columns that are used in journal calculations
        key_columns = [
            'Item', 'Created At Date', '# of Pax', 'Payment Type', 'Payment or Refund',
            'Subtotal Paid', 'Tax Paid', 'Total Paid',
            'Affiliate', 'Receivable from Affiliate', 'Received from Affiliate',
            'Payable to Affiliate', 'Paid to Affiliate',
            'Gross Payments', 'Refund Gross'
        ]

        # Filter to only include columns that exist in the data
        available_columns = [col for col in key_columns if col in v2_detailed_records.columns]
        v2_detailed_records = v2_detailed_records[available_columns]

        # Get fee mappings for detailed fee breakdown
        fee_mappings = execute_query("""
            SELECT t.name as tour_name, f.name as fee_name, f.per_person_amount
            FROM tour_fees tf
            JOIN tours t ON tf.tour_id = t.id
            JOIN fees f ON tf.fee_id = f.id
            ORDER BY t.name, f.name
        """)

        # Add fee breakdown columns
        if fee_mappings:
            fee_mappings_df = pd.DataFrame(fee_mappings, columns=['tour_name', 'fee_name', 'per_person_amount'])
            fee_mappings_df['per_person_amount'] = pd.to_numeric(fee_mappings_df['per_person_amount'], errors='coerce').fillna(0)

            # Get unique fee names for column headers
            unique_fees = fee_mappings_df['fee_name'].unique()

            # Add fee amount columns for each fee type
            for fee_name in unique_fees:
                v2_detailed_records[f'{fee_name} Fee Amount'] = 0.0

            # Calculate fee amounts for each booking
            for idx, row in v2_detailed_records.iterrows():
                tour_name = row.get('Item', '')
                num_pax = pd.to_numeric(row.get('# of Pax', 0), errors='coerce')

                if tour_name and num_pax > 0:
                    # Get fees for this tour
                    tour_fees = fee_mappings_df[fee_mappings_df['tour_name'] == tour_name]

                    # Calculate each fee amount
                    for _, fee_row in tour_fees.iterrows():
                        fee_name = fee_row['fee_name']
                        per_person_amount = fee_row['per_person_amount']
                        total_fee_amount = per_person_amount * num_pax

                        if f'{fee_name} Fee Amount' in v2_detailed_records.columns:
                            v2_detailed_records.at[idx, f'{fee_name} Fee Amount'] = total_fee_amount

            # Add total fees column
            fee_amount_columns = [f'{fee_name} Fee Amount' for fee_name in unique_fees]
            v2_detailed_records['Total Fees'] = v2_detailed_records[fee_amount_columns].sum(axis=1)

            # Add net subtotal (Subtotal Paid minus Total Fees)
            if 'Subtotal Paid' in v2_detailed_records.columns:
                v2_detailed_records['Subtotal Paid (Ex. Other Fees)'] = pd.to_numeric(v2_detailed_records['Subtotal Paid'], errors='coerce').fillna(0) - v2_detailed_records['Total Fees']

        # Add calculated columns used in journal
        if 'Subtotal Paid' in v2_detailed_records.columns and 'Tax Paid' in v2_detailed_records.columns:
            v2_detailed_records['Total Amount (Subtotal + Tax)'] = pd.to_numeric(v2_detailed_records['Subtotal Paid'], errors='coerce').fillna(0) + pd.to_numeric(v2_detailed_records['Tax Paid'], errors='coerce').fillna(0)

        # Split VAT by transaction type (Payment or Refund)
        if 'Tax Paid' in v2_detailed_records.columns and 'Payment or Refund' in v2_detailed_records.columns:
            v2_detailed_records['VAT_Amount'] = pd.to_numeric(v2_detailed_records['Tax Paid'], errors='coerce').fillna(0)

            # Separate VAT for payments and refunds
            v2_detailed_records['VAT_Payments'] = v2_detailed_records.apply(
                lambda row: row['VAT_Amount'] if row['Payment or Refund'] == 'Payment' else 0, axis=1
            )
            v2_detailed_records['VAT_Refunds'] = v2_detailed_records.apply(
                lambda row: abs(row['VAT_Amount']) if row['Payment or Refund'] == 'Refund' else 0, axis=1
            )

        # Add transaction type indicators
        v2_detailed_records['Transaction_Type'] = v2_detailed_records['Payment or Refund'].map({
            'Payment': 'Revenue',
            'Refund': 'Refund'
        }).fillna('Unknown')

        # Add V2 indicator
        v2_detailed_records['V2_Filter_Status'] = 'Included (Affiliate payments not yet received)'

        return v2_detailed_records

    except Exception as e:
        st.error(f"❌ Error creating V2 detailed records: {str(e)}")
        return pd.DataFrame()


def get_quickbooks_mappings():
    """Retrieve QuickBooks account mappings from database"""
    try:
        mappings = execute_query("""
            SELECT mapping_type, fareharbour_item, quickbooks_account, account_type, quickbooks_account_id
            FROM quickbooks_mappings
            WHERE is_active = true
            ORDER BY mapping_type, fareharbour_item
        """)

        if mappings:
            mapping_dict = {
                'tour_revenue': {},
                'fee_revenue': {},
                'payment_type': {},
                'processing_fee_expense': {},
                'sales_vat_liability': {}
            }

            for mapping in mappings:
                mapping_type, fareharbour_item, quickbooks_account, account_type, quickbooks_account_id = mapping
                mapping_dict[mapping_type][fareharbour_item] = {
                    'account': quickbooks_account,
                    'account_type': account_type,
                    'account_id': quickbooks_account_id
                }

            return mapping_dict
        else:
            st.warning("⚠️ No QuickBooks mappings found in database. Using fallback mappings.")
            return get_fallback_mappings()

    except Exception as e:
        st.error(f"❌ Error retrieving QuickBooks mappings: {str(e)}")
        return get_fallback_mappings()


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
        },
        'processing_fee_expense': {
            'Processing Fees': {'account': 'Processing Fee Expense', 'account_type': 'expense', 'account_id': ''}
        },
        'sales_vat_liability': {
            'Sales VAT': {'account': 'Sales Tax Payable', 'account_type': 'liability', 'account_id': ''}
        }
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


def create_tour_pivot_table(df):
    """Create pivot table summarizing data by tour with fee splits from database"""
    try:
        # Separate affiliate and direct bookings for pivot table (exclude affiliates)
        affiliate_bookings = df[df['Affiliate'].notna() & (df['Affiliate'] != '')].copy()
        direct_bookings = df[~(df['Affiliate'].notna() & (df['Affiliate'] != ''))].copy()

        # Define the columns we want to aggregate
        pivot_columns = {
            'Item': 'Tour Name',
            '# of Pax': 'Total Guests',
            'Subtotal Paid': 'Subtotal Paid',  # Ex-VAT revenue amount
            'Tax Paid': 'Tax Paid',  # VAT amount
            'Payment Gross': 'Gross Payments',
            'Refund Gross': 'Total Refunds',
            'Receivable from Affiliate': 'Receivable from Affiliate',
            'Received from Affiliate': 'Received from Affiliate'
        }

        # Check which columns exist in the dataframe
        available_columns = {k: v for k, v in pivot_columns.items() if k in df.columns}

        if 'Item' not in available_columns:
            st.error("❌ 'Item' column not found in CSV. Cannot create pivot table.")
            return pd.DataFrame()

        # Group by Item and aggregate - ONLY DIRECT BOOKINGS
        agg_dict = {}
        for col, label in available_columns.items():
            if col == 'Item':
                continue  # Skip the groupby column
            elif col == '# of Pax':
                agg_dict[col] = 'sum'  # Sum total guests
            else:
                agg_dict[col] = 'sum'  # Sum financial amounts

        # Ensure Total Tax is numeric before aggregation
        if 'Total Tax' in df.columns:
            # Handle both string values with $ signs and already numeric values
            if df['Total Tax'].dtype == 'object':
                df['Total Tax'] = pd.to_numeric(df['Total Tax'].str.replace('$', '').str.replace(',', ''), errors='coerce').fillna(0)
            else:
                df['Total Tax'] = pd.to_numeric(df['Total Tax'], errors='coerce').fillna(0)

        if not agg_dict:
            st.error("❌ No numeric columns found for aggregation.")
            return pd.DataFrame()

        # Create the pivot table - ONLY DIRECT BOOKINGS (exclude affiliate bookings)
        pivot_df = direct_bookings.groupby('Item').agg(agg_dict).reset_index()

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
