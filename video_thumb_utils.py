import os
from pathlib import Path

import cv2
from PIL import Image


def get_video_thumbnail(video_path, thumb_size=200):
    """
    Gera uma miniatura PIL.Image de um frame do vídeo (primeiro frame válido).
    Requer opencv-python (cv2).
    """
    if not os.path.exists(video_path):
        return None
    try:
        cap = cv2.VideoCapture(video_path)
        success, frame = cap.read()
        cap.release()
        if not success or frame is None:
            return None
        # Converte BGR para RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        img.thumbnail((thumb_size, thumb_size))
        return img
    except Exception:
        return None
