from functools import wraps
from flask import session, redirect, url_for, flash


def _redirect_home_by_user_type(user):
    """Mengarahkan user ke halaman utama sesuai tipe akunnya (airport vs airline)."""
    if user and user.get('user_type') == 'airline':
        return redirect(url_for('airline_portal.dashboard'))
    return redirect(url_for('dashboard.index'))


def menu_required(menu_key):
    """
    Mengecek apakah user sudah login, sesuai portalnya, dan memiliki hak akses ke menu_key.
    Kompatibel untuk internal (airport) maupun maskapai (airline).
    """
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
                return _redirect_home_by_user_type(user)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def airport_required(f):
    """Hanya mengizinkan petugas internal InJourney Airports (user_type == 'airport')."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))

        if user.get('user_type') != 'airport':
            flash('Akses ditolak. Halaman ini khusus petugas internal bandara.', 'danger')
            return redirect(url_for('airline_portal.dashboard'))

        return f(*args, **kwargs)
    return decorated_function


def airline_required(f):
    """Hanya mengizinkan user maskapai (user_type == 'airline')."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))

        if user.get('user_type') != 'airline':
            flash('Halaman tersebut khusus portal maskapai.', 'info')
            return redirect(url_for('dashboard.index'))

        return f(*args, **kwargs)
    return decorated_function