import streamlit as st
from dotenv import load_dotenv
import os
import re
import cv2
import math
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai

import subprocess
import uuid

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

prompt = '''
You are an academic video summarizer. Your job is to:
1. Carefully read the transcript below.
2. Identify and summarize all important concepts in bullet points.
3. For each concept, include the timestamp in [mm:ss] format.
4. Do not miss any key educational content.
5. If a concept is repeated, refer back to the first timestamp.

Here is the transcript with timestamps:
'''

def download_youtube_video(url, output_filename="video.mp4"):
    try:
        # Attempt to use pytube
        yt = YouTube(url)
        stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        if stream is None:
            raise Exception("No progressive streams available.")
        return stream.download(filename=output_filename)
    
    except Exception as e:
        print(f"[pytube] Failed: {e}")
        # Fallback to yt-dlp
        try:
            print("[yt-dlp] Trying fallback...")
            result = subprocess.run([
                "yt-dlp", "-f", "mp4", "-o", output_filename, url
            ], check=True)
            return output_filename
        except subprocess.CalledProcessError as ytdlp_error:
            raise RuntimeError(f"yt-dlp also failed: {ytdlp_error}")

# Extract specific frame from timestamp
def extract_frame(video_path, timestamp_sec, output_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_number = int(fps * timestamp_sec)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    success, frame = cap.read()
    if success:
        cv2.imwrite(output_path, frame)
    cap.release()

# Get transcript with timestamps
def extract_transcript_details(youtube_video_url):
    try:
        video_id = youtube_video_url.split("v=")[1]
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        return video_id, transcript_data
    except Exception as e:
        st.error(f"Transcript extraction failed: {e}")
        return None, None

# Generate summary with Gemini
def generate_gemini_content(transcript_data, prompt):
    full_text = "\n".join([f"[{entry['start']//60:.0f}:{int(entry['start'])%60:02d}] {entry['text']}" for entry in transcript_data])
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt + full_text)
    return response.text

# Streamlit App
st.title("Academic Notes with Exact Video Frames")

youtube_link = st.text_input("Enter YouTube Video Link:")

if youtube_link and st.button("Generate Academic Notes with Frames"):
    video_id, transcript_data = extract_transcript_details(youtube_link)

    if transcript_data:
        summary = generate_gemini_content(transcript_data, prompt)
        st.markdown("### Academic Notes:")

        # Download video
        video_path = download_youtube_video(youtube_link)

        # Extract timestamps
        timestamps = re.findall(r"\[(\d+):(\d{2})\]", summary)
        shown_frames = set()

        for line in summary.splitlines():
            timestamp_match = re.search(r"\[(\d+):(\d{2})\]", line)
            if timestamp_match:
                minutes, seconds = map(int, timestamp_match.groups())
                total_seconds = minutes * 60 + seconds
                key = f"{minutes}:{seconds}"
                if key not in shown_frames:
                    frame_path = f"frame_{minutes}_{seconds}.jpg"
                    extract_frame(video_path, total_seconds, frame_path)
                    st.image(frame_path, caption=f"Key Concept at [{key}]", use_container_width=True)
                    shown_frames.add(key)
                    os.remove(frame_path)
            st.write(line)

        # Clean up downloaded video
        os.remove(video_path)
        st.success("Academic notes generated successfully!")