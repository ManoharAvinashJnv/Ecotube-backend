import os
import re
import uuid
import threading
from yt_dlp import YoutubeDL

def get_default_download_dir():
    local_path = os.path.join(os.getcwd(), "downloads")
    os.makedirs(local_path, exist_ok=True)
    return local_path

DOWNLOAD_DIR = get_default_download_dir()

job_registry = {}
job_registry_lock = threading.Lock()

def sanitize_filename(name):
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    return re.sub(r'\s+', " ", cleaned).strip()

def get_unique_filepath(directory, base_filename, ext):
    safe_base = sanitize_filename(base_filename) or "media"
    candidate = os.path.join(directory, f"{safe_base}.{ext}")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{safe_base} ({counter}).{ext}")
        counter += 1
    return candidate

def analyze_media(url):
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'format': 'all',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web', 'mweb']
            }
        }
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {'success': False, 'error': 'Could not retrieve media metadata.'}
                
            title = info.get('title', 'Unknown Title')
            duration = info.get('duration', 0)
            thumbnail = info.get('thumbnail', '')
            formats = info.get('formats', [])
            
            available_video_resolutions = set()
            has_audio = False
            
            for f in formats:
                if f.get('vcodec') != 'none':
                    height = f.get('height')
                    if height:
                        if height >= 2160: available_video_resolutions.add('4K')
                        elif height >= 1440: available_video_resolutions.add('1440p')
                        elif height >= 1080: available_video_resolutions.add('1080p')
                        elif height >= 720: available_video_resolutions.add('720p')
                        elif height >= 480: available_video_resolutions.add('480p')
                        elif height >= 360: available_video_resolutions.add('360p')
                        elif height >= 240: available_video_resolutions.add('240p')
                        elif height >= 144: available_video_resolutions.add('144p')
                if f.get('acodec') != 'none':
                    has_audio = True

            quality_order = ['4K', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p', 'Best Available']
            sorted_qualities = [q for q in quality_order if q in available_video_resolutions] or ['Best Available']

            return {
                'success': True,
                'title': title,
                'duration': duration,
                'thumbnail': thumbnail,
                'qualities': sorted_qualities,
                'has_audio': has_audio
            }
    except Exception as e:
        return {'success': False, 'error': f"Analysis error: {str(e)}"}

def progress_hook(d, job_id):
    with job_registry_lock:
        if job_id not in job_registry:
            return
        status = d.get('status')
        if status == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded_bytes = d.get('downloaded_bytes', 0)
            percent = round((downloaded_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0.0
            
            job_registry[job_id].update({
                'status': 'downloading',
                'progress': percent,
                'downloaded_bytes': downloaded_bytes,
                'total_bytes': total_bytes,
                'speed': d.get('speed', 0) or 0,
                'eta': d.get('eta', 0) or 0,
                'message': f'Downloading... {percent}%'
            })
        elif status == 'finished':
            job_registry[job_id].update({
                'status': 'processing',
                'progress': 100,
                'message': 'Processing file on server...'
            })

def run_download_job(job_id, url, mode, quality, audio_format):
    try:
        with job_registry_lock:
            job_registry[job_id]['status'] = 'extracting'
            job_registry[job_id]['message'] = 'Initializing extraction...'

        info_opts = {
            'quiet': True,
            'skip_download': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'mweb']
                }
            }
        }
        title = 'media'
        with YoutubeDL(info_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if info_dict:
                title = info_dict.get('title', 'media')

        ydl_opts = {
            'progress_hooks': [lambda d: progress_hook(d, job_id)],
            'noplaylist': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'mweb']
                }
            }
        }

        if mode == 'video':
            res_map = {
                '4K': 'bestvideo[height<=2160]+bestaudio/best',
                '1440p': 'bestvideo[height<=1440]+bestaudio/best',
                '1080p': 'bestvideo[height<=1080]+bestaudio/best',
                '720p': 'bestvideo[height<=720]+bestaudio/best',
                '480p': 'bestvideo[height<=480]+bestaudio/best',
                '360p': 'bestvideo[height<=360]+bestaudio/best',
                'Best Available': 'bestvideo+bestaudio/best'
            }
            ydl_opts['format'] = res_map.get(quality, 'bestvideo+bestaudio/best')
            ydl_opts['merge_output_format'] = 'mp4'
            out_filepath = get_unique_filepath(DOWNLOAD_DIR, f"{title} [{quality}]", "mp4")
            ydl_opts['outtmpl'] = out_filepath
            final_filename = os.path.basename(out_filepath)
        else:
            ydl_opts['format'] = 'bestaudio/best'
            ext = audio_format if audio_format in ['mp3', 'm4a', 'opus'] else 'mp3'
            out_base = get_unique_filepath(DOWNLOAD_DIR, title, ext)
            ydl_opts['outtmpl'] = os.path.splitext(out_base)[0] + '.%(ext)s'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': ext,
            }]
            final_filename = os.path.basename(os.path.splitext(out_base)[0] + f".{ext}")

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        with job_registry_lock:
            job_registry[job_id]['status'] = 'completed'
            job_registry[job_id]['progress'] = 100
            job_registry[job_id]['filename'] = final_filename
            job_registry[job_id]['message'] = 'Download completed successfully!'

    except Exception as e:
        with job_registry_lock:
            job_registry[job_id]['status'] = 'failed'
            job_registry[job_id]['error'] = str(e)
            
