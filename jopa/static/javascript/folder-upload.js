document.addEventListener('submit', function (event) {
  const form = event.target;
  const folderInput = form.querySelector('input[name="download_folder"]');
  if (!folderInput) return;

  let pathsInput = form.querySelector('input[name="download_folder_paths"]');
  if (!pathsInput) {
    pathsInput = document.createElement('input');
    pathsInput.type = 'hidden';
    pathsInput.name = 'download_folder_paths';
    form.appendChild(pathsInput);
  }
  pathsInput.value = JSON.stringify(Array.from(folderInput.files, file => file.webkitRelativePath || file.name));
}, true);
