let ws;
const statusMap = new Map();

function connectWebSocket() {
    ws = new WebSocket(`ws://${window.location.host}/ws`);
    
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'status_update') {
            updateFileStatus(data.file, data.status);
        }
    };

    ws.onclose = function() {
        console.log('WebSocket connection closed. Attempting to reconnect...');
        setTimeout(connectWebSocket, 1000);
    };
}

function updateFileStatus(fileName, status) {
    const statusBadge = document.querySelector(`[data-file="${fileName}"] .status-badge`);
    if (statusBadge) {
        statusBadge.textContent = status;
        statusBadge.className = `status-badge badge ${status === 'complete' ? 'bg-success' : 'bg-primary'}`;
    }
}

async function loadFiles() {
    try {
        const response = await fetch('/list-files');
        const data = await response.json();
        const fileList = document.getElementById('fileList');
        fileList.innerHTML = '';

        data.files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'list-group-item d-flex justify-content-between align-items-center';
            item.setAttribute('data-file', file);
            
            item.innerHTML = `
                ${file}
                <div>
                    <button class="btn btn-primary btn-sm" onclick="startDownload('${file}')">Download</button>
                    <span class="status-badge badge bg-secondary">pending</span>
                </div>
            `;
            fileList.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading files:', error);
    }
}

async function startDownload(fileName) {
    try {
        const response = await fetch(`/start-download/${fileName}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (response.ok) {
            updateFileStatus(fileName, 'downloading');
        } else {
            console.error('Error starting download:', data);
        }
    } catch (error) {
        console.error('Error starting download:', error);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    loadFiles();
    // Refresh file list periodically
    setInterval(loadFiles, 30000);
});
