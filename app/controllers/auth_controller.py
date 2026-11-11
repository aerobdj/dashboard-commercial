from flask import Blueprint, render_template, request, redirect, url_for, session

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Sementara testing static dulu sebelum koneksi tabel Supabase
        if username == 'admin' and password == 'admin123':
            session['user_id'] = '1'
            session['nama'] = 'Admin Bandara'
            session['role'] = 'admin'
            return redirect(url_for('dashboard.index'))
        else:
            return render_template('auth/login.html', error="Username/Password Salah!")

    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))