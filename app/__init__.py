import os
from flask import Flask
from supabase import create_client, Client

supabase: Client = None

def create_app():
    app = Flask(__name__, template_folder='views/templates')
    app.secret_key = 'super-secret-key-airport'  # Kunci rahasia session

    # Koneksi Supabase
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    global supabase
    if url and key:
        supabase = create_client(url, key)

    # Register Controller (Blueprints)
    from app.controllers.auth_controller import auth_bp
    from app.controllers.dashboard_controller import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    return app