FROM python:3.12-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg procps vim curl && rm -rf /var/lib/apt/lists/*

# Set up the working directory
WORKDIR /app

# Copy the necessary files
COPY stream_monitor.py .
COPY default_streams.json ./streams.json

RUN mkdir templates
COPY templates ./templates

RUN mkdir images
COPY templates/testscreen.jpg ./images/

# Install Flask
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 9118

# Run FastAPI with Uvicorn
CMD ["python", "stream_monitor.py"]