from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from .models import User
from . import db, bcrypt
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps
import re
from datetime import datetime, timedelta

auth = Blueprint('auth', __name__)

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, "Password is valid"

@auth.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        errors = []
        
        # Username validation
        if not username:
            errors.append("Username is required")
        elif len(username) < 3:
            errors.append("Username must be at least 3 characters long")
        elif len(username) > 50:
            errors.append("Username must be less than 50 characters")
        elif not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append("Username can only contain letters, numbers, and underscores")
        
        # Email validation
        if not email:
            errors.append("Email is required")
        elif not validate_email(email):
            errors.append("Invalid email format")
        
        # Password validation
        if not password:
            errors.append("Password is required")
        else:
            is_valid, message = validate_password(password)
            if not is_valid:
                errors.append(message)
        
        # Password confirmation
        if password and password != confirm_password:
            errors.append("Passwords do not match")
        
        # Check existing users
        if email and User.query.filter_by(email=email).first():
            errors.append("Email already registered")
        
        if username and User.query.filter_by(username=username).first():
            errors.append("Username already taken")
        
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("register.html", username=username, email=email)
        
        try:
            hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
            new_user = User(
                username=username,
                email=email,
                password=hashed_password,
                created_at=datetime.utcnow()
            )
            db.session.add(new_user)
            db.session.commit()
            flash("Account created successfully! Please login.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration error: {str(e)}")
            flash("An error occurred during registration. Please try again.", "danger")
            return render_template("register.html", username=username, email=email)
    
    return render_template("register.html")
@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        next_page = request.args.get('next')
        if current_user.is_admin and next_page == url_for('main.admin'):
            return redirect(url_for('main.admin'))
        return redirect(url_for('main.home'))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        remember = True if request.form.get("remember") else False
        if not email or not password:
            flash("Please fill all fields", "warning")
            return render_template("login.html")
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            if user.is_locked():
                flash("Account locked due to multiple failed attempts. Try again later.", "danger")
                return render_template("login.html")
            
            user.reset_failed_attempts()
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(url_for("main.home"))
        else:
            if user:
                user.increment_failed_attempts()
                db.session.commit()
            flash("Invalid email or password", "danger")
    return render_template("login.html")

@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))

@auth.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("main.admin"))
        else:
            flash("You are already logged in as a regular user.", "warning")
            return redirect(url_for("main.home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        remember = True if request.form.get("remember") else False
        if not email or not password:
            flash("Please fill all fields", "warning")
            return render_template("admin_login.html")
        user = User.query.filter_by(email=email).first()
        if user and user.is_admin and bcrypt.check_password_hash(user.password, password):
            # Reset failed attempts on successful login
            user.reset_failed_attempts()
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            flash("Admin login successful!", "success")
            return redirect(url_for("main.admin"))
        else:
            current_app.logger.warning(f"Failed admin login attempt for email: {email}")
            flash("Invalid admin credentials", "danger")
    
    return render_template("admin_login.html")

@auth.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user)

@auth.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        if not current_password or not new_password:
            flash("Please fill all fields", "warning")
            return redirect(url_for("auth.profile"))
        
        if not bcrypt.check_password_hash(current_user.password, current_password):
            flash("Current password is incorrect", "danger")
            return redirect(url_for("auth.profile"))
        
        is_valid, message = validate_password(new_password)
        if not is_valid:
            flash(message, "danger")
            return redirect(url_for("auth.profile"))
        
        if new_password != confirm_password:
            flash("New passwords do not match", "danger")
            return redirect(url_for("auth.profile"))
        
        current_user.password = bcrypt.generate_password_hash(new_password).decode("utf-8")
        db.session.commit()
        
        flash("Password changed successfully! Please login again.", "success")
        logout_user()
        return redirect(url_for("auth.login"))
    
    return render_template("change_password.html")