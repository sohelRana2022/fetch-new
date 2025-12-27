import os
import uuid
import threading
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
from flask_cors import CORS
import yt_dlp
import requests
from dotenv import load_dotenv

# Initialize Flask with default folders (templates/ and static/)
app = Flask(__name__)
CORS(app)

# Load environment variables
load_dotenv()

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Set the specific FFmpeg path provided
FFMPEG_PATH_RAW = r"C:\Users\sohel\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"

# Extract directory and add to PATH to ensure yt-dlp finds both ffmpeg and ffprobe
FFMPEG_DIR = os.path.dirname(FFMPEG_PATH_RAW)
if os.path.exists(FFMPEG_DIR):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ["PATH"]

# Global dictionary to track tasks
tasks = {}

# YouTube Data API Key
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def background_download(task_id, url, quality, output_template, ffmpeg_dir):
    try:
        def progress_hook(d):
            if d['status'] == 'downloading':
                # Extract progress info
                p = d.get('_percent_str', '0%').replace('%', '')
                s = d.get('_speed_str', 'N/A')
                e = d.get('_eta_str', 'N/A')
                
                tasks[task_id].update({
                    'status': 'downloading',
                    'progress': p,
                    'speed': s,
                    'eta': e
                })
            elif d['status'] == 'finished':
                tasks[task_id].update({
                    'status': 'processing',
                    'progress': '100'
                })

        ydl_opts = {
            'outtmpl': output_template,
            'nocheckcertificate': True,
            'ffmpeg_location': ffmpeg_dir,
            'prefer_ffmpeg': True,
            'merge_output_format': 'mp4',
            'progress_hooks': [progress_hook],
            'quiet': True
        }

        if quality == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio[ext=m4a]/bestaudio',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            if quality == '1080p':
                ydl_opts['format'] = 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best'
            elif quality == '720p':
                ydl_opts['format'] = 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best'
            else:
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        tasks[task_id]['status'] = 'finished'

    except Exception as e:
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['error'] = str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tasks')
def get_tasks():
    return jsonify(tasks)

@app.route('/api/search', methods=['POST'])
def search_video():
    data = request.json
    query = data.get('query')
    page_token = data.get('pageToken')
    if not query:
        return jsonify({'error': 'No query provided'}), 400

    try:
        # Use YouTube Data API
        search_url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'maxResults': 10,
            'q': query,
            'type': 'video',
            'key': YOUTUBE_API_KEY
        }
        if page_token:
            params['pageToken'] = page_token
        
        response = requests.get(search_url, params=params)
        data = response.json()
        
        results = []
        for item in data.get('items', []):
            video_id = item['id']['videoId']
            results.append({
                'id': video_id,
                'title': item['snippet']['title'],
                'thumbnail': item['snippet']['thumbnails']['high']['url'],
                'url': f"https://www.youtube.com/watch?v={video_id}"
            })
            
        return jsonify({'results': results, 'nextPageToken': data.get('nextPageToken')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/suggestions', methods=['POST'])
def get_suggestions():
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({'results': []})
    
    try:
        url = f"http://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={query}"
        response = requests.get(url)
        data = response.json()
        # data format is [query, [suggestion1, suggestion2, ...]]
        suggestions = data[1] if len(data) > 1 else []
        return jsonify({'results': suggestions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/info', methods=['POST'])
def get_info():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Simplified formats for UI
            formats = [
                {'id': 'mp3', 'label': 'Audio Only (MP3)'},
                {'id': 'best_mp4', 'label': 'Best Quality (MP4)'},
                {'id': '1080p', 'label': '1080p (MP4)'},
                {'id': '720p', 'label': '720p (MP4)'}
            ]
            
            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': formats,
                'original_url': url
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    quality = data.get('quality', 'best_mp4')
    
    # Unique filename to prevent collisions
    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    # Initialize task
    tasks[file_id] = {
        'id': file_id,
        'status': 'pending',
        'progress': '0',
        'speed': '0',
        'eta': '0',
        'quality': quality,
        'file_id': file_id # Used to find file later
    }

    # Start background thread
    thread = threading.Thread(
        target=background_download, 
        args=(file_id, url, quality, output_template, FFMPEG_DIR)
    )
    thread.start()

    return jsonify({'task_id': file_id})

@app.route('/api/get_file/<task_id>')
def get_file(task_id):
    task = tasks.get(task_id)
    if not task or task['status'] != 'finished':
        return jsonify({'error': 'File not ready or task not found'}), 404

    final_ext = 'mp3' if task['quality'] == 'mp3' else 'mp4'
    file_path = os.path.join(DOWNLOAD_FOLDER, f"{task['file_id']}.{final_ext}")
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found on server'}), 404

    # Schedule file deletion after sending
    @after_this_request
    def remove_file(response):
        try:
            os.remove(file_path)
            # Optional: Remove task from dictionary to free memory
            # tasks.pop(task_id, None) 
        except Exception as e:
            print(f"Error removing file: {e}")
        return response

    return send_file(file_path, as_attachment=True, download_name=f"download_{task_id}.{final_ext}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)