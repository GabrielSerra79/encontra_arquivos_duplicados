import os

from video_thumb_utils import get_video_thumbnail


def gerar_thumb_video(path, size):
    try:
        thumb_img = get_video_thumbnail(path, thumb_size=size)
        return thumb_img
    except Exception:
        return None


def existe_video(path):
    return os.path.exists(path)

# Outros utilitários de vídeo podem ser adicionados aqui
