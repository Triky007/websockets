let ws;
const statusMap = new Map();

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        document.getElementById('connectionStatus').innerHTML = `
            <span class="badge bg-success">Connected</span>
        `;
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
        document.getElementById('connectionStatus').innerHTML = `
            <span class="badge bg-danger">Disconnected</span>
        `;
        // Intentar reconectar después de 5 segundos
        setTimeout(connectWebSocket, 5000);
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'status_update') {
                updateFileStatus(data.file, data.status);
            }
        } catch (error) {
            console.error('Error processing WebSocket message:', error);
        }
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        document.getElementById('connectionStatus').innerHTML = `
            <span class="badge bg-danger">Error</span>
        `;
    };
}

function updateFileStatus(fileName, status) {
    const fileItem = document.querySelector(`[data-file="${fileName}"]`);
    if (fileItem) {
        const statusBadge = fileItem.querySelector('.status-badge');
        if (statusBadge) {
            statusBadge.className = `status-badge badge ${getStatusClass(status)}`;
            statusBadge.textContent = status;
        }
    }
}

function getStatusClass(status) {
    switch (status) {
        case 'downloading':
            return 'bg-primary';
        case 'complete':
            return 'bg-success';
        case 'error':
            return 'bg-danger';
        default:
            return 'bg-secondary';
    }
}

async function loadFiles() {
    try {
        const response = await fetch('/list-files');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        displayFiles(data.files);
    } catch (error) {
        console.error('Error loading files:', error);
        showError('Error loading files');
    }
}

function displayFiles(files) {
    const fileList = document.getElementById('fileList');
    fileList.innerHTML = '';
    
    if (files.length === 0) {
        fileList.innerHTML = '<div class="list-group-item">No files available</div>';
        return;
    }

    files.forEach(file => {
        const item = document.createElement('div');
        item.className = 'list-group-item d-flex justify-content-between align-items-center';
        item.setAttribute('data-file', file);
        
        item.innerHTML = `
            <span>${file}</span>
            <div>
                <button class="btn btn-primary btn-sm me-2" onclick="startDownload('${file}')">
                    <i class="bi bi-download"></i> Download
                </button>
                <button class="btn btn-danger btn-sm" onclick="deleteFile('${file}')">
                    <i class="bi bi-trash"></i> Delete
                </button>
                <span class="status-badge badge bg-secondary">pending</span>
            </div>
        `;
        fileList.appendChild(item);
    });
}

async function startDownload(fileName) {
    try {
        const response = await fetch(`/start-download/${fileName}`, {
            method: 'POST'
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        updateFileStatus(fileName, 'downloading');
        showSuccess(`Download started for ${fileName}`);
    } catch (error) {
        console.error('Error starting download:', error);
        showError('Error starting download');
    }
}

async function deleteFile(fileName) {
    if (!confirm(`Are you sure you want to delete ${fileName}?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/files/${fileName}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        await loadFiles(); // Recargar la lista después de eliminar
        showSuccess(`${fileName} deleted successfully`);
    } catch (error) {
        console.error('Error deleting file:', error);
        showError('Error deleting file');
    }
}

function showError(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger alert-dismissible fade show position-fixed top-0 end-0 m-3';
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    document.body.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

function showSuccess(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-success alert-dismissible fade show position-fixed top-0 end-0 m-3';
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    document.body.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    loadFiles();
    // Refresh file list periodically
    setInterval(loadFiles, 5000);
});
