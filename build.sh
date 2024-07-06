#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Install FFmpeg
apt-get update
apt-get install -y ffmpeg