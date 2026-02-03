import os

from PIL import Image


def verificar_corrompida(path):
    try:
        with Image.open(path) as img:
            img.verify()
        return False
    except Exception:
        return True


def gerar_miniatura(path, size):
    try:
        img = Image.open(path)
        img.thumbnail((size, size))
        return img
    except Exception:
        return None


def existe_arquivo(path):
    return os.path.exists(path)
