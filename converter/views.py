from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from .forms import UploadForm
from .models import Resume
from PyPDF2 import PdfReader
from docx import Document
from transformers import pipeline
from gtts import gTTS
import os
from django.conf import settings
from dotenv import load_dotenv
import logging
import subprocess

load_dotenv()

# Pretrained models
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-6-6")

# Sonic settings
SONIC_SCRIPT = os.path.join(settings.BASE_DIR, 'Sonic', 'sonic.py')

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

        # Summarize text (limit to ~150 words for <1 minute audio)
        summary = summarizer(text, max_length=150, min_length=100, do_sample=False)[0]['summary_text']

        # Convert to speech
        audio_path = os.path.join(settings.MEDIA_ROOT, f'{request.user.id}_resume.mp3')
        tts = gTTS(text=summary, lang='en', slow=False)
        tts.save(audio_path)

        # Generate video with Sonic.py
        photo_data = resume.photo_file.read()
        swapped_video_path = deepfake_face_swap(photo_data, audio_path)

        # Save video to model
        resume.video_file.name = f'videos/{request.user.id}_resume_video.mp4'
        resume.save()

        # Cleanup
        os.remove(audio_path)
        if os.path.exists(swapped_video_path):
            os.remove(swapped_video_path)

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

@login_required
def deepfake_face_swap(photo_data, audio_path):
    """
    Use Sonic.py (Portrait-Animation) to generate a lip-synced video from a photo and audio.
    Args:
        photo_data (bytes): Uploaded photo data (PNG/JPG).
        audio_path (str): Path to the generated audio file.
    Returns:
        str: Path to the final video file.
    """
    # Save photo temporarily
    temp_photo_path = os.path.join(settings.MEDIA_ROOT, f'temp_{os.urandom(8).hex()}.jpg')
    with open(temp_photo_path, 'wb') as f:
        f.write(photo_data)

    # Prepare output path
    output_video_path = os.path.join(settings.MEDIA_ROOT, f'output_{os.urandom(8).hex()}.mp4')

    # Path to Sonic.py script
    sonic_script_path = os.path.join(settings.BASE_DIR, 'Portrait-Animation', 'inference.py')

    # Call Sonic.py inference
    subprocess.run([
        'python', sonic_script_path,
        '--input_image', temp_photo_path,
        '--audio', audio_path,
        '--output', output_video_path
    ])

    # Cleanup temporary photo
    os.remove(temp_photo_path)

    return output_video_path

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')