from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from apscheduler.schedulers.background import BackgroundScheduler
import os
from datetime import timedelta


db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()

def create_app():
    app = Flask(__name__, template_folder='../templates')
    
    # Enhanced configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_strong_secret_key_here_change_in_production')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expense.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Session configuration
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
    app.config['REMEMBER_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    
    # File upload configuration
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    app.config['UPLOAD_EXTENSIONS'] = ['.jpg', '.png', '.jpeg', '.pdf', '.csv']
    
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    
    # Register blueprints
    from .routes import main
    from .auth import auth
    from .expenses import expenses
    
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(expenses)
    
    # Initialize scheduler safely
    from .expenses import sync_bank_transactions
    scheduler = BackgroundScheduler()
    
    # Only add job if not already added (to prevent duplicate in debug mode)
    if not scheduler.get_jobs():
        scheduler.add_job(sync_bank_transactions, 'interval', minutes=5, id='sync_bank_job')
        scheduler.start()
    
    # Ensure scheduler shuts down on app context teardown
    import atexit
    atexit.register(lambda: scheduler.shutdown())
    
    with app.app_context():
        db.create_all()
    
    return app