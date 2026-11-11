from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import supabase

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            # Authenticate via Supabase Auth
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            # Save user details in session
            session['user'] = {
                'id': response.user.id,
                'email': response.user.email
            }
            return redirect(url_for('dashboard.index'))
            
        except Exception as e:
            flash("Email atau password yang Anda masukkan salah!")
            return redirect(url_for('auth.login'))

    # PERBAIKAN: Sertakan folder 'auth/' sebelum 'login.html'
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))