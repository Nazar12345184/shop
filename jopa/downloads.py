import json
import posixpath
import tempfile
import zipfile
from django.core.files import File
from django.utils.text import slugify


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
