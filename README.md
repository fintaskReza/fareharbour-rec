# FareHarbour - QuickBooks Reconciliation Tool

A Streamlit application for reconciling FareHarbour bookings with QuickBooks transactions.

## Features

- **Missing Bookings**: Find bookings that exist in FareHarbour but not in QuickBooks *(with persistent notes)*
- **Cancelled vs Open**: Identify bookings cancelled in FareHarbour but still open in QuickBooks *(with persistent notes)*
- **Amount Differences**: Compare amounts between systems *(with persistent notes)*
- **Payment/Refund Comparison**: Detailed payment reconciliation *(with persistent notes)*
- **Persistent Notes**: Add and save notes for each discrepancy across all tables
- **Void Integration**: Void cancelled invoices directly in QuickBooks via webhook
- **Excel Export**: Export all reconciliation data with notes to Excel

## New: Persistent Notes Feature 📝

**All reconciliation tables** now include a **persistent notes system**:

### How it Works
- **Editable Notes Column**: Add notes directly in any reconciliation table for each booking discrepancy
- **Automatic Persistence**: Notes are saved to separate CSV files for each table type
- **Cross-Session Memory**: Notes persist between app restarts and data reloads
- **Export Integration**: Notes are included in Excel exports
- **Comprehensive Reporting**: All notes are included in the full reconciliation report

### Available in All Tables
1. **Missing Bookings** → `missing_bookings_notes.csv`
2. **Cancelled vs Open** → `cancelled_vs_open_notes.csv`
3. **Amount Differences** → `reconciliation_notes.csv`
4. **Payment/Refund Comparison** → `payment_refund_notes.csv`

### Usage
1. Navigate to any reconciliation tab (Missing Bookings, Cancelled vs Open, Amount Differences, or Payment/Refund Comparison)
2. Edit notes directly in the "Notes" column of the table
3. Click **"💾 Save Notes"** to persist your changes
4. Notes will automatically reload when you restart the app or reload data

### Notes File Structure
Each table type has its own CSV file with the following structure:
```csv
Booking_ID,Notes,Last_Updated
290981542,"Investigated - customer paid twice, refund processed","2024-01-15 10:30:00"
290981543,"Tax calculation error, QB amount is correct","2024-01-15 10:32:00"
```

### Management Features
- **Notes Statistics**: View count of bookings with notes for each table
- **File Information**: See file size, modification date, and total notes count per table
- **Clear All Notes**: Option to clear all notes for each table type (use with caution)
- **Unified Export**: Full reconciliation report includes all notes from all tables
- **Backup**: All CSV files can be manually backed up or version controlled

### Best Practices
- Use concise, actionable notes (max 500 characters)
- Include resolution status (e.g., "Resolved", "Pending", "Investigated")
- Note any actions taken or required follow-up
- Different note files allow for table-specific workflows
- Regular backup of all notes files is recommended

## File Requirements

### FareHarbour Bookings CSV
- Export the bookings report from FareHarbour
- Required columns: Booking ID, Contact, Total Paid, Paid Status, Cancelled?, etc.

### FareHarbour Payments CSV (Optional)
- Export the payments/refunds report from FareHarbour  
- Required columns: Payment or Refund, Booking ID, Gross, Net, Processing Fee, etc.

### QuickBooks Excel
- Export the transaction list by date from QuickBooks
- Should contain FareHarbour booking references in memo/description fields
- Required columns: Date, Amount, Open Balance, etc.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
streamlit run reconciliation_app.py
```

## QuickBooks Integration

The tool includes webhook integration for voiding cancelled invoices:
- Webhook URL: `https://n8n.fintask.ie/webhook/void_inv`
- Automatically extracts document numbers and calls your n8n workflow
- Provides progress tracking and detailed results

## Data Processing

The tool automatically:
- Cleans and standardizes booking ID formats
- Handles cancelled bookings with proper amount adjustments
- Aggregates payments and refunds by booking
- Identifies missing transactions and amount discrepancies
- Preserves user notes across sessions 