from functools import wraps
from flask import session, redirect, url_for, flash

def menu_required(menu_key):
    """Mengecek apakah user sudah login dan memiliki hak akses ke menu_key."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                flash('Silakan login terlebih dahulu.', 'warning')
                return redirect(url_for('auth.login'))

            allowed_menus = user.get('allowed_menus', [])
            if menu_key not in allowed_menus:
                flash('Anda tidak memiliki hak akses ke halaman tersebut.', 'danger')
                return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator