import json
import posixpath
import shutil
import tempfile
import uuid
import zipfile
from django.core.files import File
from django.conf import settings
from django.utils.text import slugify


UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024
MAX_UPLOAD_CHUNK_BYTES = 5 * 1024 * 1024


def folder_upload_directory(user_id, upload_id):
    upload_uuid = uuid.UUID(str(upload_id))
    return settings.BASE_DIR / 'private_uploads' / str(user_id) / str(upload_uuid)


def save_folder_upload_chunks(game, user, upload_id, manifest_json):
    directory = folder_upload_directory(user.pk, upload_id)
    manifest = json.loads(manifest_json)
    if not isinstance(manifest, list) or not manifest or len(manifest) > 2000:
        raise ValueError('Порожня або завелика папка.')

    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b') as archive_file:
        with zipfile.ZipFile(archive_file, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for file_index, item in enumerate(manifest):
                if not isinstance(item, dict):
                    raise ValueError('Некоректний список файлів.')
                path = str(item.get('path', '')).replace('\\', '/')
                path = posixpath.normpath(path).lstrip('/')
                if path in ('', '.', '..') or path.startswith('../') or '\x00' in path:
                    raise ValueError('Некоректний шлях у папці.')
                chunk_count = int(item.get('chunks', 0))
                if not 1 <= chunk_count <= 100000:
                    raise ValueError('Некоректний файл у папці.')
                with archive.open(path, 'w') as member:
                    for chunk_index in range(chunk_count):
                        chunk_path = directory / str(file_index) / str(chunk_index)
                        with chunk_path.open('rb') as chunk_file:
                            shutil.copyfileobj(chunk_file, member, length=1024 * 1024)
        archive_file.seek(0)
        archive_name = f'{slugify(game.name) or "game"}.zip'
        game.download_file.save(archive_name, File(archive_file, name=archive_name), save=True)

    shutil.rmtree(directory, ignore_errors=True)
    return True


def save_download_folder(game, uploaded_files, paths_json='[]'):
    if not uploaded_files:
        return False
    try:
        paths = json.loads(paths_json)
    except (TypeError, json.JSONDecodeError):
        paths = []

    safe_paths = []
    for index, uploaded in enumerate(uploaded_files):
        candidate = paths[index] if isinstance(paths, list) and index < len(paths) else uploaded.name
        candidate = str(candidate).replace('\\', '/')
        candidate = posixpath.normpath(candidate).lstrip('/')
        if candidate in ('', '.', '..') or candidate.startswith('../'):
            candidate = posixpath.basename(uploaded.name)
        safe_paths.append(candidate)

    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b') as archive_file:
        with zipfile.ZipFile(archive_file, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for uploaded, path in zip(uploaded_files, safe_paths):
                with archive.open(path, 'w') as member:
                    for chunk in uploaded.chunks():
                        member.write(chunk)
        archive_file.seek(0)
        archive_name = f'{slugify(game.name) or "game"}.zip'
        game.download_file.save(archive_name, File(archive_file, name=archive_name), save=True)
    return True
