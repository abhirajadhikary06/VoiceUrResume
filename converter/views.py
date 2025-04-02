from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse
from .forms import UploadForm
from .models import Resume
from PyPDF2 import PdfReader
from docx import Document
from transformers import pipeline
from gtts import gTTS
from moviepy.editor import VideoFileClip, AudioFileClip
import os
from django.conf import settings
from dotenv import load_dotenv
import logging
import requests
import time

load_dotenv()

# Pretrained models
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# D-ID API settings
D_ID_API_KEY = os.getenv('D_ID_API_KEY')
D_ID_API_URL = "https://api.d-id.com/talks"

def login_page(request):
    if request.user.is_authenticated:
        return redirect('uploads')
    return render(request, 'login.html')

@login_required
def uploads(request):
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            resume_instance = Resume(
                user=request.user,
                resume_file=request.FILES['resume'],
                photo_file=request.FILES['photo']
            )
            resume_instance.save()
            return redirect('convert', resume_id=resume_instance.id)
    else:
        form = UploadForm()
    return render(request, 'uploads.html', {'form': form})

@login_required
def convert(request, resume_id):
    try:
        resume = Resume.objects.get(id=resume_id, user=request.user)

        # Extract text from resume
        resume_path = resume.resume_file.path
        if resume_path.endswith('.pdf'):
            reader = PdfReader(resume_path)
            text = ''.join([page.extract_text() or '' for page in reader.pages])
        elif resume_path.endswith('.docx'):
            doc = Document(resume_path)
            text = '\n'.join([para.text for para in doc.paragraphs])

        # Summarize text
        summary = summarizer(text, max_length=240, min_length=200, do_sample=False)[0]['summary_text']

        # Convert to speech
        audio_path = os.path.join(settings.MEDIA_ROOT, f'{request.user.id}_resume.mp3')
        tts = gTTS(text=summary, lang='en', slow=False)
        tts.save(audio_path)

        # Face swap with D-ID
        photo_data = resume.photo_file.read()
        swapped_video_path = deepfake_face_swap(photo_data, audio_path)

        # Save video to model
        resume.video_file.name = f'videos/{request.user.id}_resume_video.mp4'
        resume.save()

        # Cleanup
        os.remove(audio_path)

        return redirect('converted', resume_id=resume.id)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in convert function: {str(e)}")
        return render(request, 'uploads.html', {'form': UploadForm(), 'error': 'An error occurred during conversion.'})

@login_required
def converted(request, resume_id):
    resume = Resume.objects.get(id=resume_id, user=request.user)
    video_url = resume.video_file.url
    return render(request, 'converted.html', {'video_url': video_url})

def deepfake_face_swap(photo_data, audio_path):
    """
    Use D-ID API to create a talking avatar video from a photo and audio.
    Args:
        photo_data (bytes): Uploaded photo data (PNG/JPG).
        audio_path (str): Path to the generated audio file.
    Returns:
        str: Path to the final video file.
    """
    # Prepare headers for D-ID API
    headers = {
        "Authorization": f"Bearer {D_ID_API_KEY}",
        "Content-Type": "application/json"
    }

    # Step 1: Upload photo and audio to D-ID
    with open(audio_path, 'rb') as audio_file:
        files = {
            'source_url': ('photo.jpg', photo_data, 'image/jpeg'),  # Assuming JPG, adjust if PNG
            'script': ('audio.mp3', audio_file, 'audio/mpeg')
        }
        payload = {
            "script": {
                "type": "audio",
                "audio_url": "to-be-filled"  # Will be updated after upload
            },
            "source_url": "to-be-filled"  # Will be updated after upload
        }

        # D-ID requires a public URL, but for simplicity, we'll use their upload endpoint
        # In practice, you might need to upload to a public bucket first (e.g., S3)
        # Here, we simulate direct upload (D-ID handles this internally via multipart)
        response = requests.post(D_ID_API_URL, headers=headers, data={"script": {"type": "audio"}}, files=files)
        if response.status_code != 201:
            raise ValueError(f"D-ID API error: {response.text}")
        
        talk_id = response.json()['id']

    # Step 2: Poll for the result
    video_url = None
    for _ in range(30):  # Poll for up to 5 minutes (adjust as needed)
        response = requests.get(f"{D_ID_API_URL}/{talk_id}", headers=headers)
        if response.status_code == 200 and response.json().get('status') == 'done':
            video_url = response.json()['result_url']
            break
        time.sleep(10)  # Wait 10 seconds between polls

    if not video_url:
        raise ValueError("D-ID video generation timed out or failed.")

    # Step 3: Download the video
    output_video_path = os.path.join(settings.MEDIA_ROOT, f'swapped_{os.urandom(8).hex()}.mp4')
    video_response = requests.get(video_url)
    with open(output_video_path, 'wb') as video_file:
        video_file.write(video_response.content)

    return output_video_path

@login_required
def logout(request):
    logout(request)
    return redirect('login')