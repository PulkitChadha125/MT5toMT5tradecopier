"""
Example: How to integrate subscription checker into your existing application

This shows different ways to add subscription verification to your apps.
"""

# ============================================
# METHOD 1: Simple Integration (Recommended)
# ============================================

from subscription_checker import check_subscription_access

# At the very start of your application
def main():
    # Check subscription first
    if not check_subscription_access():
        return  # Exit if access denied (error page already shown)
    
    # Your application code here...
    print("Welcome! Your application is running...")
    # ... rest of your code ...

if __name__ == "__main__":
    main()


# ============================================
# METHOD 2: With Custom Configuration
# ============================================

from subscription_checker import check_subscription_access

# If you want to use different API URL or project key
def main():
    if not check_subscription_access(
        api_url="http://your-server.com:8000",
        project_api_key="your-custom-api-key"
    ):
        return
    
    # Your application code...


# ============================================
# METHOD 3: Silent Check (No Error Page)
# ============================================

from subscription_checker import check_subscription_silent

def main():
    is_valid, message, data = check_subscription_silent()
    
    if not is_valid:
        print(f"Access denied: {message}")
        # Show your own custom error UI
        return
    
    days_remaining = data.get('days_remaining', 0)
    print(f"Access granted! {days_remaining} days remaining.")
    
    # Your application code...


# ============================================
# METHOD 4: Flask Application Integration
# ============================================

from flask import Flask, render_template_string, request, session, redirect, url_for
from subscription_checker import check_subscription_access, check_subscription_silent

app = Flask(__name__)
app.secret_key = 'your-secret-key'

def verify_subscription():
    """Middleware to check subscription"""
    if 'subscription_verified' not in session:
        # Check subscription
        is_valid, message, data = check_subscription_silent()
        
        if not is_valid:
            error_html = """
            <!DOCTYPE html>
            <html>
            <head><title>Access Denied</title></head>
            <body>
                <h1>Access Denied</h1>
                <p>{{ message }}</p>
                <a href="/login">Try Again</a>
            </body>
            </html>
            """
            return render_template_string(error_html, message=message), False
        
        # Store verification in session
        session['subscription_verified'] = True
        session['username'] = request.form.get('username') if request.method == 'POST' else 'user'
        session['days_remaining'] = data.get('days_remaining', 0)
    
    return None, True

@app.route('/')
def index():
    error, is_valid = verify_subscription()
    if error:
        return error
    
    return f"Welcome! {session.get('days_remaining', 0)} days remaining."


# ============================================
# METHOD 5: GUI Application (Tkinter)
# ============================================

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    from subscription_checker import check_subscription_silent
    
    def gui_app():
        # Create login window
        root = tk.Tk()
        root.title("Login Required")
        root.geometry("400x200")
        
        username_var = tk.StringVar()
        password_var = tk.StringVar()
        
        tk.Label(root, text="Username:").pack(pady=5)
        tk.Entry(root, textvariable=username_var).pack(pady=5)
        
        tk.Label(root, text="Password:").pack(pady=5)
        tk.Entry(root, textvariable=password_var, show="*").pack(pady=5)
        
        def login():
            # Temporarily override get_credentials to use GUI input
            import subscription_checker
            original_get = subscription_checker.get_credentials
            
            def gui_get_credentials():
                return username_var.get(), password_var.get()
            
            subscription_checker.get_credentials = gui_get_credentials
            
            is_valid, message, data = check_subscription_silent()
            
            subscription_checker.get_credentials = original_get
            
            if is_valid:
                root.destroy()
                # Start your main application
                main_app()
            else:
                messagebox.showerror("Access Denied", message)
        
        tk.Button(root, text="Login", command=login).pack(pady=10)
        root.mainloop()
    
    def main_app():
        # Your GUI application code here
        root = tk.Tk()
        root.title("Your Application")
        tk.Label(root, text="Welcome! Application is running...").pack(pady=50)
        root.mainloop()
    
    # Uncomment to use:
    # gui_app()
    
except ImportError:
    pass  # Tkinter not available


# ============================================
# METHOD 6: Command Line Application
# ============================================

from subscription_checker import check_subscription_access

def cli_app():
    print("="*60)
    print("MY APPLICATION")
    print("="*60)
    
    # Check subscription
    if not check_subscription_access():
        return  # Exit if denied
    
    # Your CLI application code
    print("\nApplication started successfully!")
    print("Processing data...")
    # ... rest of your code ...

if __name__ == "__main__":
    cli_app()

