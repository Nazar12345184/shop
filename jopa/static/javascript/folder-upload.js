document.addEventListener('submit', async function (event) {
  const form = event.target;
  const folderInput = form.querySelector('input[name="download_folder"]');
  if (!folderInput || !folderInput.files.length || form.dataset.folderUploaded === 'true') return;

  event.preventDefault();
  const uploadUrl = folderInput.dataset.uploadUrl;
  const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]')?.value;
  const files = Array.from(folderInput.files);
  const uploadId = crypto.randomUUID();
  const manifest = files.map(file => ({
    path: file.webkitRelativePath || file.name,
    chunks: Math.max(1, Math.ceil(file.size / (4 * 1024 * 1024))),
  }));

  let status = form.querySelector('[data-folder-upload-status]');
  if (!status) {
    status = document.createElement('p');
    status.dataset.folderUploadStatus = 'true';
    status.setAttribute('role', 'status');
    folderInput.insertAdjacentElement('afterend', status);
  }

  try {
    let sent = 0;
    for (let fileIndex = 0; fileIndex < files.length; fileIndex += 1) {
      const file = files[fileIndex];
      const chunkCount = manifest[fileIndex].chunks;
      for (let chunkIndex = 0; chunkIndex < chunkCount; chunkIndex += 1) {
        const start = chunkIndex * 4 * 1024 * 1024;
        const chunk = file.slice(start, Math.min(start + 4 * 1024 * 1024, file.size));
        const data = new FormData();
        data.append('csrfmiddlewaretoken', csrfToken || '');
        data.append('upload_id', uploadId);
        data.append('file_index', String(fileIndex));
        data.append('chunk_index', String(chunkIndex));
        data.append('chunk_count', String(chunkCount));
        data.append('chunk', chunk, 'chunk.bin');

        status.textContent = `Завантажую файли: ${fileIndex + 1}/${files.length} — ${file.name}`;
        const response = await fetch(uploadUrl, { method: 'POST', body: data, credentials: 'same-origin' });
        if (!response.ok) throw new Error(`Сервер повернув помилку ${response.status}`);
      }
      sent += 1;
    }

    const idInput = document.createElement('input');
    idInput.type = 'hidden';
    idInput.name = 'folder_upload_id';
    idInput.value = uploadId;
    form.appendChild(idInput);
    const manifestInput = document.createElement('input');
    manifestInput.type = 'hidden';
    manifestInput.name = 'folder_upload_manifest';
    manifestInput.value = JSON.stringify(manifest);
    form.appendChild(manifestInput);
    folderInput.disabled = true;
    form.dataset.folderUploaded = 'true';
    status.textContent = `Завантажено ${sent} файлів. Зберігаю гру…`;
    form.requestSubmit(event.submitter);
  } catch (error) {
    status.textContent = `Не вдалося завантажити папку: ${error.message}. Спробуй ще раз.`;
  }
}, true);
