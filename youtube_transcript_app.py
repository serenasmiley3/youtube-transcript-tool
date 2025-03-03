import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from deep_translator import GoogleTranslator
import os
import subprocess
from datetime import datetime
from urllib.parse import parse_qs, urlparse
import warnings
import logging
import tempfile
import shutil

# Suppress warnings and less important logging
warnings.filterwarnings('ignore')
logging.getLogger('watchdog.observers.inotify_buffer').setLevel(logging.ERROR)

# Initialize Streamlit page configuration
st.set_page_config(page_title="YouTube Transcript Tool", layout="wide")
st.title("YouTube Transcript Extractor and Translator")

# Load Whisper model with proper error handling
@st.cache_resource(show_spinner=False)
def load_whisper_model():
    with st.spinner("Loading Whisper model (this may take a minute the first time)..."):
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                import whisper
                model = whisper.load_model("base")
                st.success("Whisper model loaded successfully!")
                return model
        except Exception as e:
            st.error(f"Error loading Whisper: {str(e)}")
            st.error("Please make sure you've installed Whisper and FFmpeg correctly.")
            return None

# Helper function for safe directory cleanup
def safe_cleanup(path):
    try:
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        st.warning(f"Note: Couldn't clean up temporary files: {e}")

def split_text(text, max_length=1000):
    """Split text into chunks of a specified maximum length."""
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]

# Load the model
whisper_model = load_whisper_model()

# Helper function to extract video ID from URL
def extract_video_id(url):
    """Extract the video ID from a YouTube URL."""
    parsed_url = urlparse(url)
    if parsed_url.hostname in ['www.youtube.com', 'youtube.com']:
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query)['v'][0]
    elif parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    return None

# Main Streamlit interface
st.write("Enter a YouTube video URL to get its transcript and translations.")

# User inputs
video_url = st.text_input("YouTube Video URL")
translate = st.checkbox("Translate to English if not in English", value=True)

if video_url and whisper_model:
    video_id = extract_video_id(video_url)
    
    if video_id:
        try:
            # Try getting YouTube transcript first
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                for transcript in transcript_list:
                    transcript_data = transcript.fetch()
                    transcript_language = transcript.language_code
                    transcript_text = "\n".join([f"{entry['start']:.2f} - {entry['text']}" for entry in transcript_data])
                    
                    # Display original transcript immediately
                    st.subheader("Original Transcript")
                    st.info(f"Language detected: {transcript_language}")
                    st.text_area("Original Text", transcript_text, height=300)

                    # If translation is requested and language isn't English
                    if translate and transcript_language != "en":
                        # Start Google translation
                        with st.spinner("Getting quick Google translation..."):
                            try:
                                text_chunks = split_text(transcript_text)
                                translated_chunks = []
                                
                                for chunk in text_chunks:
                                    translated_chunk = GoogleTranslator(source="auto", target="en").translate(chunk)
                                    translated_chunks.append(translated_chunk)
                                
                                google_translation = " ".join(translated_chunks)
                                st.subheader("Quick Translation (via Google)")
                                st.text_area("Google Translated Text", google_translation, height=300)
                                
                            except Exception as ex:
                                st.error(f"Google translation error: {ex}")
                    break
            
            except Exception as ex:
                st.warning(f"No YouTube transcript available: {ex}")
                transcript_language = None
                transcript_text = None

            # Proceed with Whisper processing for translation
            if translate:
                with st.spinner("Processing high-quality translation with Whisper (this may take a few minutes)..."):
                    # Create temporary directory using tempfile
                    with tempfile.TemporaryDirectory() as temp_dir:
                        # Download audio
                        audio_file = os.path.join(temp_dir, f"{video_id}.mp3")
                        yt_dlp_command = (
                            f'yt-dlp --extract-audio --audio-format mp3 '
                            f'--postprocessor-args "-ar 44100 -ac 2" '
                            f'--output "{audio_file}" '
                            f'https://www.youtube.com/watch?v={video_id}'
                        )
                        subprocess.run(yt_dlp_command, check=True, shell=True)
                        
                        # Transcribe and translate with Whisper
                        result = whisper_model.transcribe(
                            audio_file,
                            task="translate"
                        )
                        whisper_text = result["text"]
                        whisper_language = result.get("language", "unknown")
                        
                        # No need to manually clean up as tempfile will handle it

                    # Display Whisper translation
                    st.subheader("High-Quality Translation (via Whisper)")
                    if not transcript_language:
                        st.info(f"Original language detected: {whisper_language}")
                    st.text_area("Whisper Translated Text", whisper_text, height=300)

        except Exception as e:
            st.error(f"Error processing video: {str(e)}")
            # Attempt to clean up any leftover temporary files
            safe_cleanup("temp_audio")
    else:
        st.error("Invalid YouTube URL. Please check the URL and try again.")

# Add some usage instructions at the bottom
st.markdown("""
---
### Instructions
1. Paste a YouTube video URL in the input field above
2. Choose whether you want automatic translation to English
3. The tool will show:
   - Original transcript (immediate)
   - Quick Google translation (fast but less accurate)
   - High-quality Whisper translation (takes longer but more accurate)

Note: Processing time for Whisper translation may vary depending on the video length.
""")