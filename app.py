from flask import Flask, request, jsonify, render_template, Response, send_file
from flask_cors import CORS
from pytube import YouTube
import os
import threading
import time
import subprocess
import logging
import shutil

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

progress_data = {}

# Function to find FFmpeg
def find_ffmpeg():
    # Check if ffmpeg is in PATH
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path

    # Check common installation locations
    common_locations = [
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/opt/homebrew/bin/ffmpeg',  # For Mac with Homebrew
        'C:\\ffmpeg\\bin\\ffmpeg.exe',  # For Windows
    ]
    for location in common_locations:
        if os.path.isfile(location):
            return location

    # If on Render, check their specific location
    render_ffmpeg = '/opt/render/project/src/.apt/usr/bin/ffmpeg'
    if os.path.isfile(render_ffmpeg):
        return render_ffmpeg

    return None

# Find FFmpeg
FFMPEG_BIN = find_ffmpeg()
if FFMPEG_BIN is None:
    logger.error("FFmpeg not found. Video merging will not be available.")
    raise SystemExit("FFmpeg is required but not found. Please install FFmpeg and make sure it's in your PATH.")
else:
    logger.info(f"FFmpeg found at: {FFMPEG_BIN}")

@app.route("/", methods=['GET'])
def serve_html_form():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data['url']
    resolution = data['format']
    download_id = str(int(time.time()))
    progress_data[download_id] = 0
    
    threading.Thread(target=process_video, args=(url, resolution, download_id)).start()
    return jsonify({"download_id": download_id})

def process_video(url, resolution, download_id):
    try:
        yt = YouTube(url, on_progress_callback=lambda stream, chunk, bytes_remaining: update_progress(download_id, bytes_remaining, stream.filesize))
        
        video_stream = yt.streams.filter(progressive=False, file_extension='mp4', resolution=resolution).first()
        if not video_stream:
            video_stream = yt.streams.filter(progressive=False, file_extension='mp4').order_by('resolution').desc().first()
        
        audio_stream = yt.streams.filter(only_audio=True).first()
        
        if not video_stream or not audio_stream:
            progress_data[download_id] = 'error: No suitable streams found'
            return
        
        video_file = f'video_{download_id}.mp4'
        audio_file = f'audio_{download_id}.mp4'
        output_file = f'output_{download_id}.mp4'
        
        logger.info(f"Downloading video: {video_file}")
        video_stream.download(filename=video_file)
        logger.info(f"Downloading audio: {audio_file}")
        audio_stream.download(filename=audio_file)
        
        logger.info("Merging video and audio with FFmpeg")
        ffmpeg_command = [
            FFMPEG_BIN,
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-strict', 'experimental',
            output_file
        ]
        
        try:
            result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
            logger.info(f"FFmpeg output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            error_message = f"FFmpeg error - Return code: {e.returncode}, Error: {e.stderr}"
            logger.error(error_message)
            progress_data[download_id] = f'error: {error_message}'
            return
        
        logger.info("Cleaning up temporary files")
        os.remove(video_file)
        os.remove(audio_file)
        
        progress_data[download_id] = 'done'
    except Exception as e:
        error_message = f"Error during video processing: {str(e)}"
        logger.error(error_message)
        progress_data[download_id] = f'error: {error_message}'

def update_progress(download_id, bytes_remaining, total_size):
    progress_percentage = int((1 - bytes_remaining / total_size) * 100)
    progress_data[download_id] = progress_percentage
    logger.debug(f"Download progress for {download_id}: {progress_percentage}%")

@app.route('/progress/<download_id>', methods=['GET'])
def progress(download_id):
    def generate():
        while True:
            progress = progress_data.get(download_id, 0)
            yield f'data: {{"progress": "{progress}"}}\n\n'
            if progress == 'done' or 'error' in str(progress):
                break
    return Response(generate(), mimetype='text/event-stream')

@app.route('/get_video/<download_id>', methods=['GET'])
def get_video(download_id):
    file_path = f'output_{download_id}.mp4'
    if os.path.exists(file_path):
        try:
            return send_file(file_path, as_attachment=True)
        finally:
            try:
                os.remove(file_path)
                logger.info(f"Deleted file: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting file: {e}")
    else:
        return "File not found", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)