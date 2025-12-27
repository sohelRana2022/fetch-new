import os
import uuid
import threading
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
from flask_cors import CORS
import yt_dlp
import requests
from dotenv import load_dotenv

# ----------------------------------
# App setup
# ----------------------------------
app = Flask(__name__)
CORS(app)

load_dotenv()

# ----------------------------------
# Config
# ----------------------------------
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
FFMPEG_DIR = os.getenv("FFMPEG_PATH", "")  # Optional

tasks = {}

# ----------------------------------
# Background downloader
# ----------------------------------
def background_download(task_id, url, quality, output_template):
    try:
        def progress_hook(d):
            if d["status"] == "downloading":
                tasks[task_id].update({
                    "status": "downloading",
                    "progress": d.get("_percent_str", "0").replace("%", ""),
                    "speed": d.get("_speed_str", "N/A"),
                    "eta": d.get("_eta_str", "N/A"),
                })
            elif d["status"] == "finished":
                tasks[task_id].update({
                    "status": "processing",
                    "progress": "100"
                })

        ydl_opts = {
            "outtmpl": output_template,
            "progress_hooks": [progress_hook],
            "merge_output_format": "mp4",
            "quiet": True,
        }

        if FFMPEG_DIR:
            ydl_opts["ffmpeg_location"] = FFMPEG_DIR

        if quality == "mp3":
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        elif quality == "1080p":
            ydl_opts["format"] = "bestvideo[height<=1080]+bestaudio/best"
        elif quality == "720p":
            ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best"
        else:
            ydl_opts["format"] = "bestvideo+bestaudio/best"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        tasks[task_id]["status"] = "finished"

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)

# ----------------------------------
# Routes
# ----------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/tasks")
def get_tasks():
    return jsonify(tasks)

@app.route("/api/search", methods=["POST"])
def search_video():
    query = request.json.get("query")
    page_token = request.json.get("pageToken")

    if not query:
        return jsonify({"error": "No query provided"}), 400

    params = {
        "part": "snippet",
        "maxResults": 10,
        "q": query,
        "type": "video",
        "key": YOUTUBE_API_KEY
    }
    if page_token:
        params["pageToken"] = page_token

    r = requests.get("https://www.googleapis.com/youtube/v3/search", params=params)
    data = r.json()

    results = [{
        "id": i["id"]["videoId"],
        "title": i["snippet"]["title"],
        "thumbnail": i["snippet"]["thumbnails"]["high"]["url"],
        "url": f"https://www.youtube.com/watch?v={i['id']['videoId']}"
    } for i in data.get("items", [])]

    return jsonify({
        "results": results,
        "nextPageToken": data.get("nextPageToken")
    })

@app.route("/api/suggestions", methods=["POST"])
def suggestions():
    query = request.json.get("query", "")
    if not query:
        return jsonify({"results": []})

    url = f"http://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={query}"
    r = requests.get(url)
    return jsonify({"results": r.json()[1]})

@app.route("/api/info", methods=["POST"])
def video_info():
    url = request.json.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    return jsonify({
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "formats": [
            {"id": "mp3", "label": "Audio (MP3)"},
            {"id": "best", "label": "Best Quality"},
            {"id": "1080p", "label": "1080p"},
            {"id": "720p", "label": "720p"},
        ],
    })

@app.route("/api/download", methods=["POST"])
def download():
    url = request.json.get("url")
    quality = request.json.get("quality", "best")

    task_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_FOLDER, f"{task_id}.%(ext)s")

    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": "0",
        "speed": "0",
        "eta": "0",
        "quality": quality,
    }

    threading.Thread(
        target=background_download,
        args=(task_id, url, quality, output_template),
        daemon=True
    ).start()

    return jsonify({"task_id": task_id})

@app.route("/api/get_file/<task_id>")
def get_file(task_id):
    task = tasks.get(task_id)
    if not task or task["status"] != "finished":
        return jsonify({"error": "File not ready"}), 404

    ext = "mp3" if task["quality"] == "mp3" else "mp4"
    file_path = os.path.join(DOWNLOAD_FOLDER, f"{task_id}.{ext}")

    if not os.path.exists(file_path):
        return jsonify({"error": "File missing"}), 404

    @after_this_request
    def cleanup(response):
        try:
            os.remove(file_path)
        except Exception:
            pass
        return response

    return send_file(file_path, as_attachment=True)

# ----------------------------------
# Entry point (for local only)
# ----------------------------------
if __name__ == "__main__":
    app.run()
