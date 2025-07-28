# 🚀 Deployment Guide: Streamlit Community Cloud

This guide will help you deploy your FareHarbour-QuickBooks Reconciliation Tool to **Streamlit Community Cloud** for free public access.

## 📋 Prerequisites

1. **GitHub Account**: You'll need a GitHub account to host your code
2. **Streamlit Account**: Sign up for free at [share.streamlit.io](https://share.streamlit.io)
3. **Repository**: Your code needs to be in a public GitHub repository

## 🎯 Step-by-Step Deployment

### Step 1: Push to GitHub

If you haven't already, push your code to a GitHub repository:

```bash
# Initialize git repository (if not already done)
git init

# Add all files
git add .

# Commit changes
git commit -m "Initial commit: FareHarbour-QuickBooks reconciliation tool"

# Add your GitHub repository as remote
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git

# Push to GitHub
git push -u origin main
```

### Step 2: Sign Up for Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"Sign up"** 
3. Choose **"Continue with GitHub"**
4. Authorize Streamlit to access your GitHub repositories

### Step 3: Deploy Your App

1. **Click "New app"** in the Streamlit Community Cloud dashboard
2. **Select your repository** from the dropdown
3. **Configure deployment settings**:
   - **Repository**: `YOUR_USERNAME/YOUR_REPOSITORY_NAME`
   - **Branch**: `main` (or your default branch)
   - **Main file path**: `reconciliation_app.py`
4. **Click "Deploy!"**

### Step 4: Wait for Deployment

- Initial deployment takes 2-5 minutes
- You'll see logs showing the installation progress
- Once complete, you'll get a public URL like: `https://your-app-name.streamlit.app`

### Step 5: Update Your README

Update the live demo link in your README.md:

```markdown
## 🚀 Live Demo

**[Access the app here](https://your-actual-app-url.streamlit.app)**
```

## ⚡ Quick Alternative: Deploy in 3 Commands

If your code is already on GitHub:

```bash
# 1. Visit share.streamlit.io and sign in with GitHub
# 2. Click "New app" → Select your repo → Deploy
# 3. Share your live URL!
```

## 🔧 Troubleshooting Deployment

### Common Issues & Solutions

**❌ Build Failed - Requirements Issue**
```
Solution: Ensure requirements.txt has exact versions:
streamlit==1.28.2
pandas==2.1.4
numpy==1.24.3
openpyxl==3.1.2
xlsxwriter==3.1.9
```

**❌ App Won't Start**
```
Solution: Check that reconciliation_app.py contains:
if __name__ == "__main__":
    main()
```

**❌ File Upload Issues**
```
Solution: Streamlit Community Cloud has file size limits.
The app handles this automatically with error messages.
```

**❌ Performance Issues**
```
Solution: Streamlit Community Cloud resources are limited.
For heavy usage, consider upgrading or using alternatives.
```

### Viewing Logs

1. Go to your app's dashboard on Streamlit Community Cloud
2. Click **"Manage app"**
3. View **"Logs"** to see any error messages

## 🔄 Updating Your Deployed App

Your app auto-updates when you push to GitHub:

```bash
# Make changes to your code
git add .
git commit -m "Update: description of changes"
git push

# App will automatically redeploy in 1-2 minutes
```

## 🎛️ App Management

### Restarting Your App
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Find your app and click **"⋮"** menu
3. Click **"Reboot"**

### Deleting Your App
1. Go to app management page
2. Click **"Settings"** → **"Delete app"**

### Making Your App Private
- Streamlit Community Cloud apps are public by default
- For private apps, you need Streamlit for Teams (paid)

## 🌐 Alternative Free Deployment Options

If Streamlit Community Cloud doesn't work for you:

### 1. Railway (Free Tier)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway init
railway up
```

### 2. Render (Free Tier)
1. Connect your GitHub repo to [Render](https://render.com)
2. Select "Web Service"
3. Use these settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `streamlit run reconciliation_app.py --server.port $PORT --server.address 0.0.0.0`

### 3. Heroku (Limited Free Tier)
```bash
# Create Procfile
echo "web: streamlit run reconciliation_app.py --server.port \$PORT --server.address 0.0.0.0" > Procfile

# Deploy to Heroku
heroku create your-app-name
git push heroku main
```

## 📊 Monitoring Your App

### Usage Analytics
- Streamlit Community Cloud provides basic usage metrics
- View in your app's management dashboard

### Performance Tips
- Files are processed in memory (no permanent storage)
- Large files may cause timeouts
- Consider adding file size warnings in your app

## 🎉 You're Live!

Once deployed, you can:
- ✅ Share your public URL with anyone
- ✅ Process reconciliation files from anywhere
- ✅ No installation required for users
- ✅ Automatic updates when you push code changes

## 📞 Need Help?

- **Streamlit Docs**: [docs.streamlit.io](https://docs.streamlit.io)
- **Community Forum**: [discuss.streamlit.io](https://discuss.streamlit.io)
- **GitHub Issues**: Create issues in your repository

---

**🎯 Pro Tip**: Once deployed, test with small sample files first to ensure everything works correctly in the cloud environment! 