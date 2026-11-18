import os
from flask import Flask, redirect, url_for, session, flash, request
from werkzeug.exceptions import RequestEntityTooLarge
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

    # Batas maksimal upload file: 30 MB
    app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024

    # Inisialisasi Supabase SDK
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    global supabase
    if url and key:
        try:
            supabase = create_client(url, key)
            print("[INFO] Berhasil terhubung ke Supabase Client.")
        except Exception as e:
            print(f"[ERROR] Gagal menghubungkan Supabase Client: {e}")

    # Import dan daftarkan Blueprints dari Controllers
    from app.controllers.auth_controller import auth_bp
    from app.controllers.dashboard_controller import dashboard_bp
    from app.controllers.user_controller import user_bp
    from app.controllers.cabang_controller import cabang_bp
    from app.controllers.role_controller import roles_bp
    from app.controllers.coa_controller import coa_bp
    from app.controllers.mitra_controller import mitra_bp
    from app.controllers.airline_controller import airline_bp
    from app.controllers.airline_user_controller import airline_user_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(cabang_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(coa_bp)
    app.register_blueprint(mitra_bp)
    app.register_blueprint(airline_bp)
    app.register_blueprint(airline_user_bp)

    # Handler jika file yang diunggah melebihi batas 30 MB
    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(e):
        flash('Ukuran file terlalu besar! Maksimal ukuran file yang diizinkan adalah 30 MB.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))

    # Route utama (/) otomatis arahkan ke Dashboard atau Login
    @app.route('/')
    def root():
        if 'user' in session:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    return app