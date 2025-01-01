"""
Rutas y funciones relacionadas con la comunicación WebSocket.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
from typing import Set

# Crear router sin prefijo para mantener las rutas WebSocket en la raíz
router = APIRouter(prefix="")
logger = logging.getLogger(__name__)

# Almacenar conexiones
connected_clients: Set[WebSocket] = set()
connected_agents: Set[WebSocket] = set()

async def send_websocket_message(websocket: WebSocket, message: dict, remove_from: set = None):
    """Envía un mensaje por WebSocket de forma segura"""
    try:
        await websocket.send_json(message)
    except WebSocketDisconnect:
        if remove_from is not None and websocket in remove_from:
            remove_from.remove(websocket)
    except Exception as e:
        logger.error(f"Error sending WebSocket message: {str(e)}")
        if remove_from is not None and websocket in remove_from:
            remove_from.remove(websocket)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket para clientes web"""
    await websocket.accept()
    connected_clients.add(websocket)
    
    try:
        # Notificar estado del agente
        await websocket.send_json({
            "type": "agent_status",
            "connected": len(connected_agents) > 0
        })
        
        while True:
            try:
                message = await websocket.receive_json()
                logger.info(f"Received message from client: {message}")
                
                # Procesar comando
                if message.get("type") == "command":
                    command = message.get("command")
                    if not command:
                        await websocket.send_json({
                            "type": "error",
                            "message": "No command specified"
                        })
                        continue
                    
                    # Enviar comando al agente
                    if not connected_agents:
                        await websocket.send_json({
                            "type": "error",
                            "message": "No agent connected"
                        })
                        continue
                    
                    logger.info(f"Sending command to agent: {command}")
                    # Enviar a todos los agentes conectados
                    for agent in connected_agents:
                        await agent.send_json(message)
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON message"
                })
                
    except WebSocketDisconnect:
        logger.info("Client disconnected")
        if websocket in connected_clients:
            connected_clients.remove(websocket)
    except Exception as e:
        logger.error(f"Error in websocket connection: {str(e)}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)

@router.websocket("/agent")
async def agent_websocket(websocket: WebSocket):
    """WebSocket para el agente"""
    await websocket.accept()
    connected_agents.add(websocket)
    logger.info("Agent connected")
    
    # Notificar a todos los clientes que el agente está conectado
    for client in connected_clients:
        await send_websocket_message(
            client,
            {"type": "agent_status", "connected": True},
            connected_clients
        )
    
    try:
        while True:
            message = await websocket.receive_json()
            logger.info(f"Received message from agent: {message}")
            # Reenviar mensaje a todos los clientes web
            for client in connected_clients:
                await send_websocket_message(client, message, connected_clients)
                
    except WebSocketDisconnect:
        logger.info("Agent disconnected")
        connected_agents.remove(websocket)
        # Notificar a los clientes que el agente se desconectó
        for client in connected_clients:
            await send_websocket_message(
                client,
                {"type": "agent_status", "connected": False},
                connected_clients
            )
    except Exception as e:
        logger.error(f"Error in agent websocket: {str(e)}")
        if websocket in connected_agents:
            connected_agents.remove(websocket)
