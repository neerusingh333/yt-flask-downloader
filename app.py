from flask import Flask, request, jsonify, render_template, Response, send_file
from flask_cors import CORS
from pytube import YouTube
import os
import threading
import time
import subprocess
import shutil
import logging

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

progress_data = {}

# Check if FFmpeg is available
FFMPEG_BIN = shutil.which('ffmpeg')
if FFMPEG_BIN is None:
    logger.warning("FFmpeg not found. Video merging will not be available.")
    FFMPEG_AVAILABLE = False
else:
    FFMPEG_AVAILABLE = True
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
    
    def download():
        try:
            yt = YouTube(url, on_progress_callback=lambda stream, chunk, bytes_remaining: update_progress(download_id, bytes_remaining, stream.filesize))
            
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
            
            if not stream or stream.resolution != resolution:
                if not FFMPEG_AVAILABLE:
                    progress_data[download_id] = 'error: FFmpeg not available for high-resolution download'
                    return
                
                video_stream = yt.streams.filter(res=resolution, file_extension='mp4').first()
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
                
                try:
                    ffmpeg_command = f'{FFMPEG_BIN} -i {video_file} -i {audio_file} -c:v copy -c:a aac {output_file}'
                    logger.info(f"Executing FFmpeg command: {ffmpeg_command}")
                    result = subprocess.run(ffmpeg_command, shell=True, check=True, capture_output=True, text=True)
                    logger.info(f"FFmpeg output: {result.stdout}")
                except subprocess.CalledProcessError as e:
                    error_message = f"FFmpeg error - Return code: {e.returncode}, Output: {e.output}, Error: {e.stderr}"
                    logger.error(error_message)
                    progress_data[download_id] = f'error: {error_message}'
                    return
                except Exception as e:
                    error_message = f"Unexpected error during FFmpeg execution: {str(e)}"
                    logger.error(error_message)
                    progress_data[download_id] = f'error: {error_message}'
                    return
                
                logger.info("Cleaning up temporary files")
                os.remove(video_file)
                os.remove(audio_file)
                
                progress_data[download_id] = 'done'
            else:
                output_file = f'output_{download_id}.mp4'
                logger.info(f"Downloading video: {output_file}")
                stream.download(filename=output_file)
                progress_data[download_id] = 'done'
        except Exception as e:
            error_message = f"Error during download: {str(e)}"
            logger.error(error_message)
            progress_data[download_id] = f'error: {error_message}'
    
    threading.Thread(target=download).start()
    return jsonify({"download_id": download_id})

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

def update_progress(download_id, bytes_remaining, total_size):
    progress_percentage = int((1 - bytes_remaining / total_size) * 100)
    progress_data[download_id] = progress_percentage
    logger.debug(f"Download progress for {download_id}: {progress_percentage}%")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)