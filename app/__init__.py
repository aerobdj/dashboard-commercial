import os
from flask import Flask, redirect, url_for, session, flash, request, render_template, jsonify
from werkzeug.exceptions import RequestEntityTooLarge
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import timedelta

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

    # Durasi sesi jika user mencentang "Keep me logged in" (7 hari)
    app.permanent_session_lifetime = timedelta(days=7)

    # Opsional: Keamanan cookie session tambahan
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

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
    from app.controllers.airline_portal_controller import airline_portal_bp
    from app.controllers.route_controller import route_bp
    from app.controllers.flight_number_controller import flight_number_bp
    from app.controllers.airline_registration_controller import airline_registration_bp
    from app.controllers.ppn_controller import ppn_bp
    from app.controllers.tarif_aeronautika_controller import tarif_aero_bp
    from app.controllers.tools_controller import tools_aero_bp
    from app.controllers.pjp2u_controller import pjp2u_bp
    from app.controllers.pejabat_ba_controller import pejabat_ba_bp
    from app.controllers.ba_document_controller import ba_doc_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(cabang_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(coa_bp)
    app.register_blueprint(mitra_bp)
    app.register_blueprint(airline_bp)
    app.register_blueprint(airline_user_bp)
    app.register_blueprint(airline_portal_bp)
    app.register_blueprint(route_bp)
    app.register_blueprint(flight_number_bp)
    app.register_blueprint(airline_registration_bp)
    app.register_blueprint(ppn_bp)
    app.register_blueprint(tarif_aero_bp)
    app.register_blueprint(tools_aero_bp)
    app.register_blueprint(pjp2u_bp)
    app.register_blueprint(pejabat_ba_bp)
    app.register_blueprint(ba_doc_bp)

    # Handler jika file yang diunggah melebihi batas 30 MB
    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(e):
        flash('Ukuran file terlalu besar! Maksimal ukuran file yang diizinkan adalah 30 MB.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))

    # Route utama (/) otomatis arahkan sesuai tipe user yang sedang login
    @app.route('/')
    def root():
        user = session.get('user')
        if user:
            if user.get('user_type') == 'airline':
                return redirect(url_for('airline_portal.dashboard'))
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(403)
    def handle_forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        # Jika dipanggil lewat fetch AJAX SPA di base.html, kembalikan fragment #main-content
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render_template('errors/404_partial.html'), 404
        return render_template('errors/404.html'), 404

    return app