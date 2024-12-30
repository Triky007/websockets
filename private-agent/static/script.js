async function loadFiles() {
    try {
        const response = await fetch('/list-files');
        const data = await response.json();
        const fileList = document.getElementById('fileList');
        fileList.innerHTML = '';

        data.files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'list-group-item d-flex justify-content-between align-items-center';
            
            item.innerHTML = `
                <span>${file}</span>
                <div>
                    <a href="/download/${file}" class="btn btn-primary btn-sm me-2" download>Download</a>
                    <button class="btn btn-danger btn-sm" onclick="deleteFile('${file}')">Delete</button>
                </div>
            `;
            fileList.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading files:', error);
    }
}

async function deleteFile(fileName) {
    if (!confirm(`Are you sure you want to delete "${fileName}"?`)) return;

    try {
        const response = await fetch(`/delete/${fileName}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (response.ok) {
            alert(`File "${fileName}" deleted successfully`);
            loadFiles(); // Refresh the file list
        } else {
            console.error('Error deleting file:', data.detail);
            alert('Failed to delete file');
        }
    } catch (error) {
        console.error('Error deleting file:', error);
        alert('Error deleting file');
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadFiles();
    setInterval(() => {
        fetch('/list-files')
            .then(() => {
                document.getElementById('connectionStatus').innerHTML = `
                    <span class="badge bg-success">Connected</span>
                `;
            })
            .catch(() => {
                document.getElementById('connectionStatus').innerHTML = `
                    <span class="badge bg-danger">Disconnected</span>
                `;
            });
    }, 5000);
})