from functools import wraps
from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, send_file
from app.services.pax_reconciliation_service import (
    SUPPORTED_AIRLINES_LIST,
    run_pax_reconciliation,
    generate_excel_bytes,
)

tools_aero_bp = Blueprint('tools_aero', __name__, url_prefix='/aeronautika/operasional/tools')


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@tools_aero_bp.route('/picture-to-pdf', methods=['GET'])
@login_required
def picture_to_pdf():
    return render_template('aeronautika/operasional/tools/picture_to_pdf.html')


@tools_aero_bp.route('/pax-reconciliation', methods=['GET'])
@login_required
def pax_reconciliation():
    return render_template(
        'aeronautika/operasional/tools/pax_reconciliation.html',
        supported_airlines=SUPPORTED_AIRLINES_LIST
    )


@tools_aero_bp.route('/pax-reconciliation/process', methods=['POST'])
@login_required
def pax_reconciliation_process():
    tapping_files = request.files.getlist('tapping_files')
    manifest_file = request.files.get('manifest_file')

    valid_tapping = [
        (f.filename, f.read())
        for f in tapping_files
        if f and f.filename
    ]

    if not valid_tapping:
        return jsonify({'error': 'Silakan unggah minimal 1 file Gate Tapping.'}), 400

    if not manifest_file or not manifest_file.filename:
        return jsonify({'error': 'Silakan unggah file Passenger Manifest (PDF/TXT).'}), 400

    manifest_bytes = manifest_file.read()
    result = run_pax_reconciliation(valid_tapping, manifest_file.filename, manifest_bytes)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@tools_aero_bp.route('/pax-reconciliation/export', methods=['POST'])
@login_required
def pax_reconciliation_export():
    payload = request.get_json(silent=True) or {}
    records = payload.get('records', [])
    airline = payload.get('airline', 'Rekonsiliasi').replace(' ', '_')

    if not records:
        return jsonify({'error': 'Tidak ada data untuk diunduh.'}), 400

    excel_stream = generate_excel_bytes(records)
    filename = f"InJourney_Rekonsiliasi_{airline}.xlsx"

    return send_file(
        excel_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )