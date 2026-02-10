# Integration Folder

This folder contains all the necessary files to integrate subscription verification into your existing applications.

## 📁 Files in This Folder

### 1. `subscription_checker.py` ⭐ **MAIN FILE**
   - **Purpose**: Core subscription verification function
   - **Usage**: Copy this file to your application and import it
   - **Features**:
     - Prompts for username/password
     - Verifies subscription with admin module
     - Shows error page if access denied
     - Captures system ID and IP address
     - Logs access attempts

### 2. `example_integration.py`
   - **Purpose**: Multiple integration examples
   - **Shows**: 6 different ways to integrate subscription checking
   - **Includes**: CLI, Flask, Tkinter, and custom implementations

### 3. `README.md` (This file)
   - **Purpose**: Overview and quick reference guide

## 🚀 Quick Start

### Step 1: Copy the File
Copy `subscription_checker.py` to your application directory.

### Step 2: Update Configuration
Edit `subscription_checker.py` and update:
```python
API_URL = "http://localhost:8000"  # Your admin module URL
PROJECT_API_KEY = "your-project-api-key-here"  # Get from admin dashboard
```

### Step 3: Add to Your Application
```python
from subscription_checker import check_subscription_access

# At the start of your application
if not check_subscription_access():
    exit()  # Access denied

# Your application code here...
```

## 📖 Usage Examples

### Simple Integration
```python
from subscription_checker import check_subscription_access

if not check_subscription_access():
    exit()

# Your code here...
```

### With Custom Configuration
```python
from subscription_checker import check_subscription_access

if not check_subscription_access(
    api_url="http://your-server.com:8000",
    project_api_key="your-api-key"
):
    exit()
```

### Silent Check (Custom Error Handling)
```python
from subscription_checker import check_subscription_silent

is_valid, message, data = check_subscription_silent()

if not is_valid:
    print(f"Error: {message}")
    # Show your custom error UI
    exit()

days_remaining = data.get('days_remaining', 0)
print(f"Access granted! {days_remaining} days remaining.")
```

## 🔧 Configuration

### Getting Your Project API Key

1. Login to admin dashboard: `http://localhost:8000`
2. Navigate to **Projects**
3. Find your project
4. Copy the **API Key**
5. Paste it in `subscription_checker.py`

### Setting Up Users

1. In admin dashboard → **Users** → Create user
2. Go to **Subscriptions**
3. Assign user to your project
4. Set expiry date

## ✨ Features

- ✅ **Automatic Verification** - One function call
- ✅ **Expiry Checking** - Blocks expired subscriptions
- ✅ **System Tracking** - Prevents credential sharing
- ✅ **IP Logging** - Tracks access locations
- ✅ **Error Pages** - Beautiful error messages
- ✅ **Easy Integration** - Works with any Python app

## 📋 Requirements

- Python 3.7+
- `requests` library
- Admin module running and accessible

Install requirements:
```bash
pip install requests
```

## 🔍 How It Works

1. User enters username and password
2. System captures machine ID and IP address
3. API call to admin module for verification
4. Checks subscription status and expiry
5. Grants or denies access
6. Logs attempt in admin dashboard

## 🛠️ Integration Types

### Command Line Applications
See `example_integration.py` - Method 6

### Web Applications (Flask)
See `example_integration.py` - Method 4

### GUI Applications (Tkinter)
See `example_integration.py` - Method 5

### Custom Applications
See `example_integration.py` - Method 3

## ❓ Troubleshooting

### Connection Error
- Ensure admin module is running
- Check API_URL is correct
- Verify network connectivity

### Invalid Credentials
- Verify username/password
- Check user exists in admin dashboard
- Ensure user has subscription

### No Active Subscription
- Assign subscription in admin dashboard
- Check expiry date
- Verify subscription is active

## 📚 Additional Resources

- See `example_integration.py` for detailed examples
- Check main `README.md` for admin module documentation
- Review admin dashboard logs for access attempts

## 📝 Notes

- The function automatically handles all error cases
- System ID prevents credential sharing
- All access attempts are logged
- Error pages are displayed automatically
- Silent mode available for custom handling

## 🔐 Security Features

- Password verification via admin module
- System fingerprinting (prevents sharing)
- IP address tracking
- Expiry date enforcement
- Access logging

---

**Ready to integrate?** Copy `subscription_checker.py` to your application and follow the quick start guide above!

