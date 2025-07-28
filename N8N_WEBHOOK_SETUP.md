# 🔗 N8N Webhook Setup Guide: Void Invoice Flow

This guide explains how to set up your n8n workflow to handle void invoice requests from the FareHarbour reconciliation tool and extract FH booking numbers.

## 📋 Overview

When the reconciliation tool finds cancelled FareHarbour bookings with open QuickBooks invoices, users can click "Void All in QuickBooks" to automatically void those invoices. This triggers your n8n webhook for each document number.

## 🎯 Webhook Endpoint

Your webhook URL: `https://n8n.fintask.ie/webhook/void_inv`

## 📥 Incoming Payload Format

The reconciliation tool sends this JSON payload for each invoice:

```json
{
    "doc_number": "INV-001234",
    "action": "void", 
    "source": "fareharbour_reconciliation"
}
```

**Parameters:**
- `doc_number`: The QuickBooks document/invoice number (from the '#' column)
- `action`: Always "void" for this use case
- `source`: Identifier showing the request came from the reconciliation tool

## 🔧 N8N Workflow Setup

### 1. Webhook Node Configuration

```javascript
// Webhook Node Settings
Method: POST
Path: void_inv
Authentication: None (or add authentication as needed)
Response Mode: Respond Immediately
Response Code: 200
```

### 2. Extract Document Number

```javascript
// Code Node: Extract Document Number
const docNumber = $json.doc_number;
const action = $json.action;

// Validate the request
if (!docNumber || action !== 'void') {
    throw new Error('Invalid request: missing doc_number or invalid action');
}

return {
    doc_number: docNumber,
    action: action,
    timestamp: new Date().toISOString()
};
```

### 3. Query QuickBooks for Invoice Details

```javascript
// HTTP Request Node: Get Invoice from QuickBooks
// This retrieves the full invoice details including memo/description

Method: GET
URL: https://your-qb-api-endpoint/v3/company/{{companyId}}/invoice/{{$json.doc_number}}
Authentication: OAuth2 or as configured
Headers:
{
    "Accept": "application/json",
    "Authorization": "Bearer {{your_access_token}}"
}
```

### 4. Extract FH Booking ID from Invoice

```javascript
// Code Node: Extract FH Booking ID
const invoiceData = $json; // QuickBooks invoice response

// FH booking IDs can be found in various fields:
// 1. In the memo/description field
// 2. In custom fields
// 3. In line item descriptions

let fhBookingId = null;

// Check memo field for FH booking ID patterns
if (invoiceData.Memo) {
    // Look for patterns like #290981542 or FH-290981542
    const memoMatch = invoiceData.Memo.match(/#?(\d{8,})|FH-(\d+)/);
    if (memoMatch) {
        fhBookingId = memoMatch[1] || memoMatch[2];
    }
}

// Check custom fields if memo doesn't contain FH ID
if (!fhBookingId && invoiceData.CustomField) {
    for (const field of invoiceData.CustomField) {
        if (field.Name && field.Name.toLowerCase().includes('fareharbour')) {
            const fieldMatch = field.StringValue.match(/\d{8,}/);
            if (fieldMatch) {
                fhBookingId = fieldMatch[0];
                break;
            }
        }
    }
}

// Check line items for FH booking references
if (!fhBookingId && invoiceData.Line) {
    for (const line of invoiceData.Line) {
        if (line.Description) {
            const lineMatch = line.Description.match(/#?(\d{8,})|FH-(\d+)/);
            if (lineMatch) {
                fhBookingId = lineMatch[1] || lineMatch[2];
                break;
            }
        }
    }
}

return {
    qb_doc_number: $json.doc_number,
    fh_booking_id: fhBookingId,
    invoice_amount: invoiceData.TotalAmt || 0,
    invoice_status: invoiceData.EmailStatus || 'Unknown',
    found_fh_id: !!fhBookingId
};
```

### 5. Void the Invoice in QuickBooks

```javascript
// HTTP Request Node: Void Invoice
// This actually voids the invoice in QuickBooks

Method: POST
URL: https://your-qb-api-endpoint/v3/company/{{companyId}}/invoice/{{$json.qb_doc_number}}/void
Authentication: OAuth2 or as configured
Headers:
{
    "Accept": "application/json", 
    "Content-Type": "application/json",
    "Authorization": "Bearer {{your_access_token}}"
}

Body:
{
    "void": true,
    "VoidReason": "Cancelled in FareHarbour - Auto-voided by reconciliation tool"
}
```

### 6. Log Results and Optional Actions

```javascript
// Code Node: Process Results
const results = {
    qb_doc_number: $json.qb_doc_number,
    fh_booking_id: $json.fh_booking_id,
    voided_successfully: $json.void_response ? true : false,
    void_timestamp: new Date().toISOString(),
    amount_voided: $json.invoice_amount
};

// Optional: Log to database, send notifications, etc.

return results;
```

## 📊 Complete Flow Structure

```
1. Webhook (void_inv) 
   ↓
2. Extract & Validate Payload
   ↓  
3. Query QB Invoice Details
   ↓
4. Extract FH Booking ID
   ↓
5. Void Invoice in QuickBooks
   ↓
6. Log Results & Notifications
```

## 🔍 Finding FH Booking IDs - Common Patterns

### Pattern 1: In Invoice Memo
```
"Booking #290981542 - John Doe"
"FareHarbour Booking: 290981542"
"Ref: #290981542"
```

### Pattern 2: In Custom Fields
```json
{
    "Name": "FareHarbour_Booking_ID",
    "StringValue": "290981542"
}
```

### Pattern 3: In Line Item Descriptions
```
"Whale Watching Tour - Booking #290981542"
"Tour for 4 people (FH: 290981542)"
```

## 🧪 Testing Your Webhook

### Test Payload
```bash
curl -X POST https://n8n.fintask.ie/webhook/void_inv \
  -H "Content-Type: application/json" \
  -d '{
    "doc_number": "TEST-001",
    "action": "void",
    "source": "fareharbour_reconciliation"
  }'
```

### Expected Response
```json
{
    "success": true,
    "message": "Invoice TEST-001 voided successfully",
    "fh_booking_id": "290981542"
}
```

## ⚠️ Error Handling

Add error handling for common scenarios:

```javascript
// Error Handling Node
const error = $json.error;

if (error) {
    // Log error
    console.error('Void process failed:', error);
    
    // Return structured error response
    return {
        success: false,
        error: error.message,
        doc_number: $json.doc_number,
        timestamp: new Date().toISOString()
    };
}
```

## 🔐 Security Considerations

1. **Authentication**: Add webhook authentication if needed
2. **Rate Limiting**: Implement rate limiting to prevent abuse
3. **Validation**: Validate document numbers before processing
4. **Logging**: Log all void operations for audit purposes

## 📝 Response Format

Your webhook should respond with:

```json
{
    "success": true,
    "message": "Invoice INV-001234 voided successfully",
    "fh_booking_id": "290981542",
    "timestamp": "2025-01-07T10:30:00Z"
}
```

## 🚀 Advanced Features

### Batch Processing
If you receive multiple void requests, consider batching them:

```javascript
// Batch multiple voids into single QB API call
const batchVoids = voidRequests.map(req => ({
    operation: "void",
    invoice_id: req.doc_number
}));
```

### Notifications
Send notifications when voiding completes:

```javascript
// Send Slack/Email notification
const notification = {
    text: `Voided ${results.length} invoices from FareHarbour reconciliation`,
    details: results
};
```

## 📋 Checklist

- [ ] Webhook endpoint configured at `/webhook/void_inv`
- [ ] Document number extraction working
- [ ] QuickBooks API integration set up
- [ ] FH booking ID extraction patterns implemented
- [ ] Void operation working in QuickBooks
- [ ] Error handling implemented
- [ ] Testing completed with sample data
- [ ] Logging/monitoring in place

Your n8n flow is now ready to handle void requests from the reconciliation tool! 