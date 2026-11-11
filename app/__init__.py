import os
from flask import Flask
from supabase import create_client, Client
from dotenv import load_dotenv  # <-- Tambahkan import ini

# Load variabel dari file .env
load_dotenv()

supabase: Client = None

def create_app():
    app = Flask(__name__, template_folder='views/templates')
    app.secret_key = 'super-secret-key-airport'

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    global supabase
    if url and key:
        supabase = create_client(url, key)

    from app.controllers.auth_controller import auth_bp
    from app.controllers.dashboard_controller import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    return app