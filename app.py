from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS
from pytube import YouTube
import os

app = Flask(__name__)
CORS(app, supports_credentials=True)  # Enable CORS with credentials

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# Serve the HTML form
@app.route("/", methods=['GET'])
def serve_html_form():
    return render_template('index.html')

@app.route('/download', methods=['POST', 'OPTIONS'])
def download_video():
    if request.method == 'OPTIONS':
        # Handle preflight request
        return '', 200

    data = request.json
    url = data['url']
    format = data['format']

    try:
        yt = YouTube(url)
        resolution_map = {
            "360p": "360p",
            "480p": "480p",
            "720p": "720p"
        }

        stream = yt.streams.filter(res=resolution_map[format], file_extension='mp4').first()

        if not stream:
            return jsonify({"error": "Stream not found"}), 404

        file_path = 'video.mp4'
        stream.download(filename=file_path)
        return send_file(file_path, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
