import os
from flask import Flask
from supabase import create_client, Client
from dotenv import load_dotenv

# Muat variabel lingkungan dari .env
load_dotenv()

# Global Client Supabase
supabase: Client = None

def create_app():
    # Set folder template dan static sesuai struktur MVC
    app = Flask(
        __name__, 
        template_folder='views/templates', 
        static_folder='static'
    )
    
    # Secret key untuk mengelola session Flask (Flash messages, login session)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secret-key-airport-commercial-2026")

    # Inisialisasi Supabase SDK
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    global supabase
    if url and key:
        try:
            supabase = create_client(url, key)
        except Exception as e:
            print(f"[ERROR] Gagal menghubungkan Supabase Client: {e}")

    # Import dan daftarkan Blueprints dari Controllers
    from app.controllers.auth_controller import auth_bp
    from app.controllers.dashboard_controller import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    return app