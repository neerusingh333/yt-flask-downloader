from flask import Flask, request, jsonify, render_template, Response, send_file
from flask_cors import CORS
from pytube import YouTube
import os
import threading
import time
import subprocess

app = Flask(__name__)
CORS(app, supports_credentials=True)

progress_data = {}

# Check if FFmpeg is available
try:
    subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    FFMPEG_AVAILABLE = True
except FileNotFoundError:
    FFMPEG_AVAILABLE = False
    print("Warning: FFmpeg not found. Video merging will not be available.")

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

@app.route("/", methods=['GET'])
def serve_html_form():
    return render_template('index.html')

@app.route('/download', methods=['POST', 'OPTIONS'])
def download_video():
    if request.method == 'OPTIONS':
        return '', 200
    
    data = request.json
    url = data['url']
    resolution = data['format']
    download_id = str(int(time.time()))
    progress_data[download_id] = 0
    
    def download():
        try:
            yt = YouTube(url, on_progress_callback=lambda stream, chunk, bytes_remaining: update_progress(download_id, bytes_remaining, stream.filesize))
            
            # Try to get the highest quality progressive stream
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
                
                video_stream.download(filename=video_file)
                audio_stream.download(filename=audio_file)
                
                # Merge video and audio using FFmpeg
                try:
                    ffmpeg_command = f'ffmpeg -i {video_file} -i {audio_file} -c:v copy -c:a aac {output_file}'
                    subprocess.run(ffmpeg_command, shell=True, check=True)
                except subprocess.CalledProcessError as e:
                    progress_data[download_id] = f'error: FFmpeg error - {str(e)}'
                    return
                
                # Clean up temporary files
                os.remove(video_file)
                os.remove(audio_file)
                
                progress_data[download_id] = 'done'
            else:
                output_file = f'output_{download_id}.mp4'
                stream.download(filename=output_file)
                progress_data[download_id] = 'done'
        except Exception as e:
            progress_data[download_id] = f'error: {str(e)}'
    
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
        return send_file(file_path, as_attachment=True)
    else:
        return "File not found", 404

def update_progress(download_id, bytes_remaining, total_size):
    progress_percentage = int((1 - bytes_remaining / total_size) * 100)
    progress_data[download_id] = progress_percentage

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)