from flask import Blueprint, render_template, session, redirect, url_for

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
def index():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    # PERBAIKAN: Sertakan folder 'dashboard/' sebelum 'index.html'
    return render_template('dashboard/index.html', user=session['user'])