from flask import Flask, render_template, request
import re
import time
import threading
import webbrowser

app = Flask(__name__)

def get_video_id(url):
    if "watch?v=" in url:
        return url.split("watch?v=")[-1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return ""

def open_video(url, loop_duration):
    loop_url = f"{url}?autoplay=1&loop=1&playlist={get_video_id(url)}"
    webbrowser.open(loop_url)
    time.sleep(loop_duration)  # Loop duration

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        youtube_url = request.form.get("youtube_url")
        video_count = int(request.form.get("video_count", 1))
        loop_duration = int(request.form.get("loop_duration", 10))  # Get loop duration in seconds
        video_id = get_video_id(youtube_url)
        
        if video_id:
            threading.Thread(target=open_video, args=(youtube_url, loop_duration)).start()
            return render_template("video_grid.html", video_id=video_id, video_count=video_count)
        else:
            return "Invalid YouTube URL. Please try again."
    
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)