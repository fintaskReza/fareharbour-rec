# 🔐 Secure Deployment Guide

## ⚠️ Security Warning

**THIS APPLICATION HANDLES SENSITIVE FINANCIAL DATA AND CAN VOID QUICKBOOKS INVOICES**

Do NOT deploy this as a public application without implementing the security measures outlined below.

## 🚨 Current Security Risks

### If Deployed Publicly Without Security:
- ❌ Anyone can access sensitive financial data
- ❌ Anyone can void QuickBooks invoices causing financial damage
- ❌ No authentication or access controls
- ❌ Webhook endpoints exposed
- ❌ Potential for data theft or manipulation

## ✅ Recommended Deployment Approach

### Step 1: Implement Security Measures

I've already added basic security features to your app:

1. **Password Authentication**: Added login screen
2. **Feature Flags**: Void functionality can be disabled
3. **Environment Variables**: Sensitive config moved to env vars
4. **API Key Support**: Webhook authentication capability

### Step 2: Configure Environment Variables

Set these in your deployment platform:

```bash
# REQUIRED: Change this password!
APP_PASSWORD="your-very-secure-password-here"

# RECOMMENDED: Disable void feature for maximum security
ENABLE_VOID_FEATURE="false"

# Your actual webhook URL (not the default)
WEBHOOK_URL="https://your-n8n-instance.com/webhook/void_inv"

# Optional but recommended for webhook security
API_KEY="your-webhook-api-key"
```

### Step 3: Deploy to Streamlit Community Cloud (Secured)

1. **Push Updated Code to GitHub**:
```bash
git add .
git commit -m "Add security features for deployment"
git push origin main
```

2. **Deploy on Streamlit Cloud**:
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Create new app from your GitHub repo
   - Point to `app.py` as main file

3. **Configure Secrets**:
   - In app settings, go to "Secrets" tab
   - Add your environment variables:
   ```toml
   APP_PASSWORD = "your-secure-password-here"
   ENABLE_VOID_FEATURE = "false"
   WEBHOOK_URL = "https://your-actual-webhook-url.com"
   API_KEY = "your-api-key"
   ```

### Step 4: Test Security

1. **Verify Authentication**: App should require password
2. **Verify Void Disabled**: Should show "Void feature disabled" message
3. **Test with Sample Data**: Upload test files to ensure functionality
4. **Verify Webhook Security**: Test that API key is sent correctly

## 🛡️ Additional Security Recommendations

### For Higher Security Needs:

1. **Private Deployment**:
   - Use Streamlit for Teams (paid) for private apps
   - Or deploy on private cloud (AWS, GCP, Azure)
   - Use VPN access only

2. **Enhanced Authentication**:
   - Implement OAuth (Google, Microsoft) instead of password
   - Add user roles and permissions
   - Session timeouts

3. **Data Security**:
   - Add file encryption
   - Implement audit logging
   - Data retention policies

4. **Network Security**:
   - IP whitelisting
   - HTTPS only
   - Rate limiting

## 🚀 Quick Secure Deployment Steps

```bash
# 1. Update your code with security features (already done)
git add .
git commit -m "Add security features"
git push

# 2. Deploy to Streamlit Community Cloud
# - Go to share.streamlit.io
# - Connect your GitHub repo
# - Set main file to "app.py"

# 3. Configure secrets in Streamlit dashboard
# - Add APP_PASSWORD with strong password
# - Set ENABLE_VOID_FEATURE="false"
# - Add your webhook URL and API key

# 4. Test and verify security measures work
```

## 📋 Security Checklist

Before going live:

- [ ] Changed default password to strong password (20+ characters)
- [ ] Set ENABLE_VOID_FEATURE="false" 
- [ ] Configured proper webhook URL (not the example)
- [ ] Added API key for webhook authentication
- [ ] Tested authentication works
- [ ] Tested with sample data files
- [ ] Verified void feature is disabled
- [ ] Documented access procedures for your team
- [ ] Planned regular security reviews
- [ ] Set up backup procedures for QuickBooks data
- [ ] Tested webhook security

## 🆘 If You Need to Deploy Immediately

**Minimum Security** (if you must deploy now):

1. Set strong `APP_PASSWORD`
2. Set `ENABLE_VOID_FEATURE="false"`
3. Monitor access closely
4. Plan security improvements ASAP

**Better**: Wait until you can implement proper security

**Best**: Deploy privately or on internal network only

## 📞 Getting Help

If you need help with:
- Setting up private deployment
- Implementing additional security
- OAuth integration
- Audit logging

Consider hiring a security consultant or developer familiar with financial applications.

---

**Remember**: Financial applications require higher security standards. Take the time to implement proper security measures before deployment. 