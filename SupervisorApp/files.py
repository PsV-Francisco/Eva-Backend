from pathlib import Path

from django import forms
from PIL import Image, UnidentifiedImageError


MAX_EVIDENCE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {
    '.jpg': 'JPEG',
    '.jpeg': 'JPEG',
    '.png': 'PNG',
}


def validate_evidence_file(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower()
    if uploaded_file.size > MAX_EVIDENCE_SIZE:
        raise forms.ValidationError('El archivo no puede superar los 5 MB.')

    if extension in ALLOWED_IMAGE_FORMATS:
        try:
            image = Image.open(uploaded_file)
            image.verify()
            if image.format != ALLOWED_IMAGE_FORMATS[extension]:
                raise forms.ValidationError('El contenido no coincide con el formato de imagen indicado.')
        except (UnidentifiedImageError, OSError) as error:
            raise forms.ValidationError('El archivo no contiene una imagen JPG o PNG válida.') from error
        finally:
            uploaded_file.seek(0)
    elif extension == '.pdf':
        signature = uploaded_file.read(5)
        uploaded_file.seek(0)
        if signature != b'%PDF-':
            raise forms.ValidationError('El archivo no contiene un documento PDF válido.')
    else:
        raise forms.ValidationError('Usa una imagen JPG/PNG o un documento PDF.')

    return uploaded_file
