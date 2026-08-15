import os
import re
import uuid
import threading
import requests
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

def is_youtube_url(url):
    return 'youtube.com' in url or 'youtu.be' in url

def analyze_media(url):
    # YouTube Fallback API (Bypasses Render Datacenter Block)
    if is_youtube_url(url):
        try:
            api_res = requests.post(
                "https://api.cobalt.tools/api/json",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={"url": url},
                timeout=10
            )
            data = api_res.json()
            if data.get("status") in ["stream", "redirect", "picker"]:
                return {
                    'success': True,
                    'title': 'YouTube Video',
                    'duration': 0,
                    'thumbnail': '',
                    'qualities': ['Best Available', '1080p', '720p', '480p', '360p'],
                    'has_audio': True
                }
        except Exception:
            pass # Fallback to yt-dlp if API is busy

    # Standard yt-dlp for Instagram, Twitter, FB & YouTube Fallback
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
            for f in formats:
                if f.get('vcodec') != 'none':
                    height = f.get('height')
                    if height:
                        if height >= 1080: available_video_resolutions.add('1080p')
                        elif height >= 720: available_video_resolutions.add('720p')
                        elif height >= 480: available_video_resolutions.add('480p')
                        elif height >= 360: available_video_resolutions.add('360p')

            quality_order = ['1080p', '720p', '480p', '360p', 'Best Available']
            sorted_qualities = [q for q in quality_order if q in available_video_resolutions] or ['Best Available']

            return {
                'success': True,
                'title': title,
                'duration': duration,
                'thumbnail': thumbnail,
                'qualities': sorted_qualities,
                'has_audio': True
            }
    except Exception as e:
        return {'success': False, 'error': f"Media error: {str(e)}"}

def run_download_job(job_id, url, mode, quality, audio_format):
    try:
        with job_registry_lock:
            job_registry[job_id]['status'] = 'downloading'
            job_registry[job_id]['message'] = 'Processing media link...'

        # YouTube Bypass via Direct Stream API
        if is_youtube_url(url):
            try:
                payload = {"url": url}
                if mode == "audio":
                    payload["downloadMode"] = "audio"
                    payload["audioFormat"] = audio_format if audio_format in ['mp3', 'm4a'] else 'mp3'

                res = requests.post(
                    "https://api.cobalt.tools/api/json",
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    json=payload,
                    timeout=30
                )
                data = res.json()
                media_url = data.get("url")
                
                if media_url:
                    ext = "mp3" if mode == "audio" else "mp4"
                    filename = f"YouTube_Media_{job_id[:6]}.{ext}"
                    filepath = os.path.join(DOWNLOAD_DIR, filename)

                    file_data = requests.get(media_url, stream=True)
                    with open(filepath, 'wb') as f:
                        for chunk in file_data.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    with job_registry_lock:
                        job_registry[job_id]['status'] = 'completed'
                        job_registry[job_id]['progress'] = 100
                        job_registry[job_id]['filename'] = filename
                        job_registry[job_id]['message'] = 'Download completed successfully!'
                    return
            except Exception:
                pass

        # Standard yt-dlp handling for non-YouTube links
        ydl_opts = {
            'noplaylist': True,
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'%(title)s [{job_id[:4]}].%(ext)s'),
        }

        if mode == 'video':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
        else:
            ydl_opts['format'] = 'bestaudio/best'
            ext = audio_format if audio_format in ['mp3', 'm4a'] else 'mp3'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': ext}]

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        with job_registry_lock:
            job_registry[job_id]['status'] = 'completed'
            job_registry[job_id]['progress'] = 100
            job_registry[job_id]['filename'] = os.path.basename(filename)
            job_registry[job_id]['message'] = 'Download completed successfully!'

    except Exception as e:
        with job_registry_lock:
            job_registry[job_id]['status'] = 'failed'
            job_registry[job_id]['error'] = str(e)
            
