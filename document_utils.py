import os

from PIL import Image, ImageDraw, ImageFont


def gerar_miniatura_documento(path, size):
    ext = os.path.splitext(path)[1].lower()
    thumb_img = Image.new('RGB', (size, size), color="#568ece")  # azul
    draw = ImageDraw.Draw(thumb_img)
    try:
        font_size = int(size * 0.28)
        font = ImageFont.truetype('arial.ttf', font_size)
    except Exception:
        font = ImageFont.load_default()
    ext_txt = ext.upper()[1:6] if len(ext) > 1 else 'DOC'
    # Pillow >=10: font.getbbox, Pillow <10: font.getsize
    try:
        bbox = font.getbbox(ext_txt)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        # Fallback: centraliza aproximadamente
        w, h = size // 2, int(size * 0.3)
    draw.text(((size-w)//2, (size-h)//2), ext_txt, fill='white', font=font)
    return thumb_img


def existe_documento(path):
    return os.path.exists(path)
