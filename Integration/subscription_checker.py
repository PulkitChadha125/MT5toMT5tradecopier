"""
Subscription Checker Function
Add this to your existing applications to verify user subscriptions.

Usage:
    from subscription_checker import check_subscription_access
    
    # At the start of your application
    if not check_subscription_access():
        exit()  # Access denied, function already showed error page
    
    # Your application code here...
"""

import requests
import platform
import hashlib
import socket
import json
import sys
from datetime import datetime
from typing import Optional, Tuple

# Configuration - UPDATE THESE VALUES
API_URL = "http://localhost:8000"  # Your admin module URL
PROJECT_API_KEY = "your-project-api-key-here"  # Get this from admin dashboard


def get_system_id() -> str:
    """Generate a unique system ID based on machine characteristics."""
    try:
        machine_info = {
            'hostname': platform.node(),
            'platform': platform.platform(),
            'processor': platform.processor(),
            'machine': platform.machine()
        }
        info_string = json.dumps(machine_info, sort_keys=True)
        return hashlib.sha256(info_string.encode()).hexdigest()[:32]
    except Exception:
        return hashlib.sha256(platform.node().encode()).hexdigest()[:32]


def get_ip_address() -> str:
    """Get the public IP address."""
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        if response.status_code == 200:
            return response.json().get('ip', 'unknown')
    except Exception:
        pass
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return 'unknown'


def show_error_page(message: str, expired: bool = False):
    """Display a simple HTML error page."""
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Access Denied</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 2rem;
        }}
        .error-container {{
            background: rgba(30, 41, 59, 0.95);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(168, 85, 247, 0.3);
            border-radius: 1.5rem;
            padding: 3rem;
            max-width: 500px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .error-icon {{
            width: 100px;
            height: 100px;
            margin: 0 auto 2rem;
            background: linear-gradient(135deg, #ef4444, #dc2626);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 3rem;
            color: white;
            box-shadow: 0 0 30px rgba(239, 68, 68, 0.5);
        }}
        h1 {{
            color: #ffffff;
            font-size: 2rem;
            margin-bottom: 1rem;
        }}
        p {{
            color: #cbd5e1;
            font-size: 1.1rem;
            line-height: 1.6;
            margin-bottom: 1.5rem;
        }}
        .contact-info {{
            background: rgba(168, 85, 247, 0.1);
            border: 1px solid rgba(168, 85, 247, 0.3);
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-top: 2rem;
        }}
        .contact-info h3 {{
            color: #ffffff;
            margin-bottom: 0.5rem;
        }}
        .contact-info p {{
            color: #94a3b8;
            font-size: 0.95rem;
            margin-bottom: 0.25rem;
        }}
        .btn {{
            display: inline-block;
            padding: 0.75rem 2rem;
            background: linear-gradient(135deg, #a855f7, #ec4899);
            color: white;
            text-decoration: none;
            border-radius: 0.5rem;
            font-weight: 600;
            margin-top: 1rem;
            transition: transform 0.2s ease;
        }}
        .btn:hover {{
            transform: translateY(-2px);
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">
            {'⏰' if expired else '🚫'}
        </div>
        <h1>{'Subscription Expired' if expired else 'Access Denied'}</h1>
        <p>{message}</p>
        <div class="contact-info">
            <h3>📞 Contact Administrator</h3>
            <p>Please contact the administrator to:</p>
            <p>• Renew your subscription</p>
            <p>• Get access to this application</p>
            <p>• Resolve any access issues</p>
        </div>
        <a href="javascript:location.reload()" class="btn">Try Again</a>
    </div>
</body>
</html>
"""
    print(html)
    sys.exit(1)


def get_credentials() -> Tuple[str, str]:
    """Prompt user for username and password."""
    print("\n" + "="*60)
    print("SUBSCRIPTION VERIFICATION REQUIRED")
    print("="*60)
    username = input("\nEnter Username: ").strip()
    password = input("Enter Password: ").strip()
    return username, password


def check_subscription_access(api_url: str = None, project_api_key: str = None) -> bool:
    """
    Check if user has valid subscription access.
    
    Args:
        api_url: Admin module API URL (defaults to global API_URL)
        project_api_key: Project API key (defaults to global PROJECT_API_KEY)
    
    Returns:
        True if access granted, False otherwise (shows error page)
    
    Usage:
        if not check_subscription_access():
            exit()  # Access denied
        # Continue with your application
    """
    # Use provided values or defaults
    api_url = api_url or API_URL
    project_api_key = project_api_key or PROJECT_API_KEY
    
    # Get credentials
    username, password = get_credentials()
    
    if not username or not password:
        show_error_page("Username and password are required.")
        return False
    
    # Get system info
    system_id = get_system_id()
    ip_address = get_ip_address()
    
    try:
        # Verify subscription
        response = requests.post(
            f'{api_url}/api/verify',
            json={
                'username': username,
                'password': password,
                'api_key': project_api_key,
                'system_id': system_id,
                'ip_address': ip_address
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('valid'):
                days_remaining = data.get('days_remaining', 0)
                print(f"\n✓ Access granted! Days remaining: {days_remaining}")
                print("="*60 + "\n")
                return True
            else:
                # Access denied
                message = data.get('message', 'Access denied')
                expired = data.get('expired', False)
                show_error_page(message, expired)
                return False
        else:
            show_error_page("Unable to verify subscription. Please try again later.")
            return False
            
    except requests.exceptions.RequestException as e:
        show_error_page(f"Connection error: Unable to reach subscription server.\n\nPlease check your internet connection and try again.")
        return False
    except Exception as e:
        show_error_page(f"Error: {str(e)}")
        return False


def check_subscription_silent(api_url: str = None, project_api_key: str = None) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    Check subscription without showing error page (for programmatic use).
    
    Returns:
        Tuple of (is_valid, message, data)
    """
    api_url = api_url or API_URL
    project_api_key = project_api_key or PROJECT_API_KEY
    
    username, password = get_credentials()
    
    if not username or not password:
        return False, "Username and password are required", None
    
    system_id = get_system_id()
    ip_address = get_ip_address()
    
    try:
        response = requests.post(
            f'{api_url}/api/verify',
            json={
                'username': username,
                'password': password,
                'api_key': project_api_key,
                'system_id': system_id,
                'ip_address': ip_address
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('valid', False), data.get('message'), data
        else:
            return False, "API request failed", None
            
    except Exception as e:
        return False, f"Error: {str(e)}", None


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("SUBSCRIPTION CHECKER - TEST MODE")
    print("="*60)
    print("\n⚠️  IMPORTANT: Update API_URL and PROJECT_API_KEY")
    print("   at the top of this file before using!\n")
    
    # Test the function
    if check_subscription_access():
        print("✓ Subscription verified! Application can continue...")
        # Your application code would go here
    else:
        print("✗ Access denied!")

