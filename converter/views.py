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
from moviepy import VideoFileClip, AudioFileClip
import cv2
import numpy as np
from insightface.app import FaceAnalysis
import os
from django.conf import settings
from dotenv import load_dotenv
import logging

load_dotenv()

# Pretrained models
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

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

        # Face swap
        stock_video = VideoFileClip("converter/static/stock_speaking_video.mp4")
        photo_data = resume.photo_file.read()
        swapped_video_path = deepfake_face_swap(stock_video, photo_data)

        # Combine audio and video
        final_video = VideoFileClip(swapped_video_path).set_audio(AudioFileClip(audio_path))
        output_path = os.path.join(settings.MEDIA_ROOT, f'{request.user.id}_resume_video.mp4')
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac')

        # Save video
        resume.video_file.name = f'videos/{request.user.id}_resume_video.mp4'
        resume.save()

        # Cleanup
        os.remove(audio_path)
        os.remove(swapped_video_path)

        return redirect('converted', resume_id=resume.id)
    except Exception as e:
        # Log the error for debugging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in convert function: {str(e)}")
        return render(request, 'uploads.html', {'form': UploadForm(), 'error': 'An error occurred during conversion.'})

@login_required
def converted(request, resume_id):
    resume = Resume.objects.get(id=resume_id, user=request.user)
    video_url = resume.video_file.url
    return render(request, 'converted.html', {'video_url': video_url})

def deepfake_face_swap(video_clip, photo_data):
    app = FaceAnalysis()  # Initialize the FaceAnalysis app
    app.prepare(ctx_id=0, det_size=(640, 640))  # Prepare the app with appropriate settings
    photo_array = np.frombuffer(photo_data, np.uint8)
    source_img = cv2.imdecode(photo_array, cv2.IMREAD_COLOR)
    source_faces = app.get(source_img)
    if not source_faces:
        raise ValueError("No face detected in photo!")
    source_face = source_faces[0]

    temp_video_path = os.path.join(settings.MEDIA_ROOT, 'temp_video.mp4')
    output_video = os.path.join(settings.MEDIA_ROOT, f'swapped_{os.urandom(8).hex()}.mp4')
    video_clip.write_videofile(temp_video_path, codec='libx264', audio=False, logger=None)

    cap = cv2.VideoCapture(temp_video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video, fourcc, fps, (width, height))  # Corrected variable name

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        faces = app.get(frame)
        if faces:
            for face in faces:
                frame = swapper.get(frame, face, source_face, paste_back=True)
        out.write(frame)

    cap.release()
    out.release()
    os.remove(temp_video_path)
    return output_video

@login_required
def logout(request):
    logout(request)  # Log the user out
    return redirect('login')
