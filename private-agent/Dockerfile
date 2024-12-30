# Dockerfile para el Agente Privado

# 1. Usar la imagen oficial de Python
FROM python:3.11-slim

# 2. Configurar el directorio de trabajo
WORKDIR /app

# 3. Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. Copiar archivos necesarios
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar el resto de los archivos del proyecto
COPY . .

# 6. Crear directorio para archivos descargados
RUN mkdir -p files

# 7. Exponer el puerto en el que correrá el agente
EXPOSE 8001

# 8. Ejecutar la aplicación
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8001"]
