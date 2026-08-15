import os
import time
import shutil
import uuid
import threading
from flask import Flask, render_template, request, jsonify, send_from_directory
from downloader import analyze_media, run_download_job, job_registry, job_registry_lock, DOWNLOAD_DIR

app = Flask(__name__)

WA_STATUS_DIR = "/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media/.Statuses"
WA_BUSINESS_STATUS_DIR = "/storage/emulated/0/Android/media/com.whatsapp.w4b/WhatsApp Business/Media/.Statuses"

def start_cleanup_scheduler():
    def auto_cleanup():
        while True:
            time.sleep(1800)
            now = time.time()
            try:
                for f in os.listdir(DOWNLOAD_DIR):
                    f_path = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.isfile(f_path) and (now - os.path.getmtime(f_path)) > 3600:
                        os.remove(f_path)
            except Exception:
                pass
    t = threading.Thread(target=auto_cleanup, daemon=True)
    t.start()

start_cleanup_scheduler()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'error': 'Please provide a valid media URL.'}), 400
    result = analyze_media(url)
    return jsonify(result), (200 if result['success'] else 400)

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    mode = data.get('mode', 'video')
    quality = data.get('quality', 'Best Available')
    audio_format = data.get('audio_format', 'mp3')
    
    if not url:
        return jsonify({'success': False, 'error': 'URL is required.'}), 400
        
    job_id = str(uuid.uuid4())
    
    with job_registry_lock:
        job_registry[job_id] = {
            'status': 'queued',
            'progress': 0,
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'speed': 0,
            'eta': 0,
            'message': 'Queued for download...',
            'error': None
        }
        
    thread = threading.Thread(
        target=run_download_job,
        args=(job_id, url, mode, quality, audio_format),
        daemon=True
    )
    thread.start()
    return jsonify({'success': True, 'job_id': job_id})

@app.route('/api/progress/<job_id>', methods=['GET'])
def api_progress(job_id):
    with job_registry_lock:
        job_info = job_registry.get(job_id)
    if not job_info:
        return jsonify({'success': False, 'error': 'Job ID not found.'}), 404
    return jsonify({'success': True, **job_info})

@app.route('/api/files/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

@app.route('/api/whatsapp/statuses', methods=['GET'])
def get_whatsapp_statuses():
    statuses = []
    for s_dir in [WA_STATUS_DIR, WA_BUSINESS_STATUS_DIR]:
        if os.path.exists(s_dir):
            try:
                for f in os.listdir(s_dir):
                    if f.endswith(('.jpg', '.jpeg', '.mp4', '.png')):
                        statuses.append({'filename': f, 'is_video': f.endswith('.mp4')})
            except Exception:
                pass
    return jsonify({'success': True, 'statuses': statuses})

@app.route('/api/whatsapp/save', methods=['POST'])
def save_whatsapp_status():
    filename = (request.get_json() or {}).get('filename')
    if not filename: return jsonify({'success': False, 'error': 'Filename missing'}), 400
    source = None
    for s_dir in [WA_STATUS_DIR, WA_BUSINESS_STATUS_DIR]:
        possible = os.path.join(s_dir, filename)
        if os.path.exists(possible): source = possible; break
    if not source: return jsonify({'success': False, 'error': 'Status file not found'}), 404
    dest = os.path.join(DOWNLOAD_DIR, f"WA_Status_{filename}")
    shutil.copy(source, dest)
    return jsonify({'success': True, 'filename': f"WA_Status_{filename}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
  
