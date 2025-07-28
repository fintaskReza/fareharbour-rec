# Security Configuration Guide

## Required Environment Variables

Before deploying this application, you MUST set the following environment variables for security:

### Authentication
```bash
APP_PASSWORD=your_secure_password_here
```
- **Required**: Set a strong password (minimum 12 characters, mix of letters/numbers/symbols)
- **Default**: "fareharbour2024" (CHANGE THIS!)
- **Purpose**: Basic authentication to prevent unauthorized access

### Void Feature Control
```bash
ENABLE_VOID_FEATURE=false
```
- **Options**: "true" or "false" 
- **Recommended**: "false" for maximum security
- **Purpose**: Controls whether users can void QuickBooks invoices

### Webhook Configuration
```bash
WEBHOOK_URL=https://your-n8n-instance.com/webhook/void_inv
API_KEY=your_api_key_here
```
- **WEBHOOK_URL**: Your actual n8n webhook endpoint
- **API_KEY**: Optional but recommended for webhook authentication
- **Purpose**: Secure communication with your QuickBooks integration

## Deployment Options

### Option 1: Secure Private Deployment (Recommended)
1. Deploy to a private hosting service (not public)
2. Set strong `APP_PASSWORD`
3. Set `ENABLE_VOID_FEATURE=false`
4. Use VPN or IP restrictions
5. Regular security audits

### Option 2: Controlled Public Deployment
1. Set very strong `APP_PASSWORD` (20+ characters)
2. Set `ENABLE_VOID_FEATURE=false`
3. Monitor access logs regularly
4. Consider additional rate limiting
5. Regular password rotation

### Option 3: Internal Network Only
1. Deploy on internal network/intranet only
2. No public internet access
3. Standard security practices apply

## Streamlit Community Cloud Configuration

To set environment variables in Streamlit Community Cloud:

1. Go to your app settings
2. Click "Secrets" tab
3. Add each variable:
```toml
APP_PASSWORD = "your_secure_password_here"
ENABLE_VOID_FEATURE = "false"
WEBHOOK_URL = "https://your-n8n-instance.com/webhook/void_inv"
API_KEY = "your_api_key_here"
```

## Security Checklist

- [ ] Changed default password
- [ ] Set ENABLE_VOID_FEATURE=false
- [ ] Updated webhook URL to your actual endpoint
- [ ] Added API key authentication
- [ ] Reviewed data handling procedures
- [ ] Planned regular security reviews
- [ ] Documented access procedures for team
- [ ] Set up monitoring/logging if possible

## Risk Mitigation

Even with these security measures:

1. **Limited Access**: Only give credentials to authorized users
2. **Regular Audits**: Review access logs and user activity
3. **Data Minimization**: Only upload necessary data files
4. **Backup Security**: Secure your n8n webhook endpoint
5. **Incident Response**: Have a plan for security incidents

## Production Deployment Warning

⚠️ **WARNING**: This application processes sensitive financial data and can perform destructive operations (voiding invoices). Ensure you have:

- Proper backups of QuickBooks data
- Tested the void functionality in a QB sandbox first
- Limited access to authorized personnel only
- Monitoring and alerting in place
- Clear procedures for data handling 