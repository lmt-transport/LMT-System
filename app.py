import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from datetime import datetime
import os
import json

app = Flask(__name__)
CORS(app)

SHEET_NAME = 'LMT_Database'

def connect_to_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if 'GOOGLE_CREDENTIALS' in os.environ:
            creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME)
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

# --- Routes ---
@app.route('/')
def login_page(): return render_template('login.html')
@app.route('/driver-dashboard')
def driver_dashboard(): return render_template('driver_dashboard.html')
@app.route('/admin-dashboard')
def admin_dashboard(): return render_template('admin_dashboard.html')

# --- Auth API ---
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username, password = str(data.get('username')), str(data.get('password'))
    sheet = connect_to_sheet()
    if not sheet: return jsonify({"status": "error"}), 500
    try:
        drivers = sheet.worksheet('Drivers').get_all_records()
        for d in drivers:
            if str(d['username']) == username and str(d['password']) == password:
                return jsonify({"status": "success", "driver": {"id": d['driver_id'], "full_name": d['full_name'], "role": d['role']}})
        return jsonify({"status": "fail"}), 401
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

# --- Job APIs ---
@app.route('/api/admin/jobs')
def get_all_jobs():
    sheet = connect_to_sheet()
    try:
        jobs = sheet.worksheet('Jobs').get_all_records()
        jobs.reverse()
        return jsonify({"status": "success", "jobs": jobs})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/driver/jobs')
def get_driver_jobs():
    driver_id = request.args.get('driver_id')
    sheet = connect_to_sheet()
    try:
        all_jobs = sheet.worksheet('Jobs').get_all_records()
        my_jobs = [j for j in all_jobs if str(j['driver_id']) == str(driver_id)]
        my_jobs.reverse()
        return jsonify({"status": "success", "jobs": my_jobs})
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/api/admin/create-job', methods=['POST'])
def create_job():
    data = request.json
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Jobs')
        new_id = f"JOB-{len(ws.get_all_values())}" 
        row = [""] * 14
        row[0], row[1] = new_id, datetime.now().strftime("%Y-%m-%d")
        row[2], row[3] = data['job_name'], "Pending"
        row[4], row[5] = data['driver_id'], data['driver_name']
        row[6] = data.get('pickup_time', '') 
        row[9] = json.dumps(data['waypoints'], ensure_ascii=False) 
        row[11] = 0 
        ws.append_row(row)
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

# [NEW] API ลบงาน
@app.route('/api/admin/delete-job', methods=['POST'])
def delete_job():
    data = request.json
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Jobs')
        cell = ws.find(data.get('job_id'))
        if not cell: return jsonify({"status": "error", "message": "Not found"}), 404
        ws.delete_rows(cell.row)
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

# [NEW] API แก้ไขงาน (เฉพาะชื่อ, คนขับ, เวลา)
@app.route('/api/admin/edit-job', methods=['POST'])
def edit_job():
    data = request.json
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Jobs')
        cell = ws.find(data.get('job_id'))
        if not cell: return jsonify({"status": "error", "message": "Not found"}), 404
        r = cell.row
        
        # Update Specific Columns (C=3:Name, E=5:DriverID, F=6:DriverName, G=7:Time)
        ws.update_cell(r, 3, data.get('job_name'))
        ws.update_cell(r, 5, data.get('driver_id'))
        ws.update_cell(r, 6, data.get('driver_name'))
        ws.update_cell(r, 7, data.get('pickup_time'))
        
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

# --- Job Interaction APIs ---
@app.route('/api/job/accept', methods=['POST'])
def accept_job():
    data = request.json
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Jobs')
        cell = ws.find(data.get('job_id'))
        if not cell: return jsonify({"status": "error"}), 404
        ws.update_cell(cell.row, 4, "Active")
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error"}), 500

@app.route('/api/job/update', methods=['POST'])
def update_job():
    data = request.json
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Jobs')
        cell = ws.find(data.get('job_id'))
        if not cell: return jsonify({"status": "error"}), 404
        r = cell.row
        new_step = int(data.get('step_index'))
        
        ws.update_cell(r, 12, new_step)
        ws.update_cell(r, 13, str(datetime.now()))
        ws.update_cell(r, 14, f"{data.get('lat')},{data.get('long')}")
        
        waypoints_json = ws.cell(r, 10).value
        waypoints = json.loads(waypoints_json)
        if new_step >= len(waypoints):
            ws.update_cell(r, 4, "Completed")

        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error"}), 500

# --- Driver Management APIs ---
@app.route('/api/admin/drivers')
def get_all_drivers():
    sheet = connect_to_sheet()
    try:
        return jsonify({"status": "success", "drivers": sheet.worksheet('Drivers').get_all_records()})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/add-driver', methods=['POST'])
def add_driver():
    data = request.json
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Drivers')
        new_id = f"DRV-{str(len(ws.get_all_values())).zfill(3)}"
        row = [new_id, data['username'], data['password'], data['full_name'], data['id_card'], data['license_plate'], data['phone'], 'driver']
        ws.append_row(row)
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/edit-driver', methods=['POST'])
def edit_driver():
    data = request.json
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Drivers')
        cell = ws.find(data['driver_id'])
        r = cell.row
        ws.update_cell(r, 2, data['username'])
        ws.update_cell(r, 3, data['password'])
        ws.update_cell(r, 4, data['full_name'])
        ws.update_cell(r, 5, data['id_card'])
        ws.update_cell(r, 6, data['license_plate'])
        ws.update_cell(r, 7, data['phone'])
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/delete-driver', methods=['POST'])
def delete_driver():
    driver_id = request.json.get('driver_id')
    sheet = connect_to_sheet()
    try:
        ws = sheet.worksheet('Drivers')
        cell = ws.find(driver_id)
        ws.delete_rows(cell.row)
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)