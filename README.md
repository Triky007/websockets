# 🚀 Gestión de Archivos con FastAPI

## 📚 Descripción
Aplicación con un **Servidor Público** y un **Agente Privado** que gestionan la descarga y gestión de archivos mediante comunicación WebSocket y endpoints protegidos.

## 🛠️ Tecnologías
- Python (FastAPI)
- WebSockets
- Docker
- JavaScript, HTML, CSS

## 📂 Estructura
- `/public-server`: Servidor principal con interfaz web.
- `/private-agent`: Agente para recibir comandos y gestionar archivos.

## ⚙️ Configuración
1. Copia los archivos `.env.template` a `.env` y configura las variables necesarias:
   ```bash
   cp public-server/.env.template public-server/.env
   cp private-agent/.env.template private-agent/.env


# File Download Manager System

This is a client-server application that consists of a public server and a private agent for secure file downloads.

## Components

### Public Server (Port 8000)
- Manages file listings and download requests
- Provides a web interface for users
- Communicates with private agents via WebSocket

### Private Agent (Port 8001)
- Downloads files from the public server
- Manages local file storage
- Provides a web interface for monitoring downloads

## Setup

1. Install dependencies for both components:

```bash
# For public server
cd public-server
pip install -r requirements.txt

# For private agent
cd ../private-agent
pip install -r requirements.txt
```

2. Configure the API key:
   - Edit the `API_KEY` variable in both `public-server/main.py` and `private-agent/agent.py`
   - Make sure they match

3. Start the servers:

```bash
# Start public server (in one terminal)
cd public-server
python main.py

# Start private agent (in another terminal)
cd private-agent
python agent.py
```

## Usage

1. Access the public server interface at: http://localhost:8000
   - View available files
   - Initiate downloads

2. Access the private agent interface at: http://localhost:8001
   - Monitor downloaded files
   - Download files locally

## Security

- Files are protected by an API key
- WebSocket communication between server and agent
- Secure file transfer protocol

## Directory Structure

```
.
├── public-server/
│   ├── main.py
│   ├── requirements.txt
│   ├── templates/
│   │   └── index.html
│   ├── static/
│   │   └── script.js
│   └── files/
└── private-agent/
    ├── agent.py
    ├── requirements.txt
    ├── templates/
    │   └── index.html
    ├── static/
    │   └── script.js
    └── files/
```
#   w e b s o c k e t s  
 