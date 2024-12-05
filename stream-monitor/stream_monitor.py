import asyncio
import os
import subprocess
import json
import time
import logging
import threading
import requests
import signal
import uvicorn
import xml.etree.ElementTree as ET
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

# Set up templates
templates = Jinja2Templates(directory="templates")

CONFIG_FILE = "streams.json"
metrics = {}
latest_images = {}
stream_info = {}
lock = threading.Lock()
stopping = False
image_counters = {}
MAX_IMAGE_ROTATION = 5
counter_lock = threading.Lock()

def handle_exit(signum, frame):
    logging.info("Received exit signal, stopping monitoring.")
    stopping = True
    os._exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

@app.on_event("shutdown")
async def shutdown_event():
    global stopping
    logging.info("Shutdown event triggered, stopping monitoring.")
    stopping = True
    # Perform other cleanup tasks here if necessary

# Configure logging
def configure_logging(level: str = "INFO"):
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)  # Remove existing handlers

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    logging.info("Logging configured successfully.")

# Load configuration
def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        logging.debug(f"Configuration loaded successfully: {config}")
        return config
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        raise

# Run ffprobe
def run_ffprobe(url):
    """Run ffprobe to gather stream information."""
    logging.debug(f"Running ffprobe on URL: {url}")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-print_format", "json", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        logging.debug(f"FFProbe output for {url}: {result.stdout}")
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logging.error(f"FFProbe timed out for URL: {url}")
    except Exception as e:
        logging.error(f"FFProbe failed for URL '{url}': {e}")
    return None

# Parse MPEG-DASH manifest
def parse_mpd_manifest(url):
    """Parse a DASH MPD manifest and extract details."""
    logging.debug(f"Fetching MPD manifest from URL: {url}")
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        root = ET.fromstring(response.text)

        drm_protection = any("ContentProtection" in child.tag for child in root.iter())
        profiles = []
        segments = 0

        for adaptation_set in root.findall(".//{urn:mpeg:dash:schema:mpd:2011}AdaptationSet"):
            for representation in adaptation_set.findall("{urn:mpeg:dash:schema:mpd:2011}Representation"):
                profiles.append({
                    "id": representation.attrib.get("id"),
                    "width": representation.attrib.get("width"),
                    "height": representation.attrib.get("height"),
                    "frameRate": representation.attrib.get("frameRate"),
                    "bandwidth": representation.attrib.get("bandwidth"),
                })
            segments += len(adaptation_set.findall(".//{urn:mpeg:dash:schema:mpd:2011}SegmentTimeline"))

        manifest_details = {"drm_protected": drm_protection, "profiles": profiles, "segments": segments}
        logging.debug(f"Manifest details for {url}: {manifest_details}")
        return manifest_details
    except requests.exceptions.Timeout:
        logging.error(f"Manifest fetch timed out for URL: {url}")
    except Exception as e:
        logging.error(f"Failed to parse manifest for URL '{url}': {e}")
    return None

# Extract image
def extract_image(url, output_path, name, width, height):
    """Extract an image from the stream using ffmpeg."""
    # Get and increment counter for this stream
    with counter_lock:
        current_counter = image_counters.get(name, 0)
        image_counters[name] = (current_counter + 1) % (MAX_IMAGE_ROTATION + 1)
    
    image_file = os.path.join(output_path, f"{name}_{current_counter}.jpg")
    logging.debug(f"Extracting image from URL: {url} into {image_file}")
    
    try:
        os.makedirs(output_path, exist_ok=True)
        command = [
            "ffmpeg", "-y", "-i", url, "-frames:v", "1", "-vf",
            f"scale={width}:{height}", "-q:v", "2", image_file
        ]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=5)
        
        # Only update the latest_images dict if the extraction was successful
        with lock:
            latest_images[name] = image_file
            
        logging.debug(f"Image extracted successfully: {image_file}")
        return image_file
    except subprocess.TimeoutExpired:
        logging.error(f"Image extraction timed out for URL: {url}")
    except Exception as e:
        logging.error(f"Failed to extract image for URL '{url}': {e}")
    return None

# Monitor streams
def monitor_streams(config):
    """Monitor streams in a loop."""
    logging.info("Starting stream monitoring loop.")

    # Global image extraction defaults
    global_image_config = config.get("image_extraction", {})
    global_enabled = global_image_config.get("enabled", True)
    global_output_path = global_image_config.get("output_path", "./images")
    global_width = global_image_config.get("width", 640)
    global_height = global_image_config.get("height", 480)
    logging.info(f"Global image extraction settings: enabled={global_enabled}, output_path={global_output_path}, width={global_width}, height={global_height}")

    while not stopping:
        for stream in config["streams"]:
            name = stream["name"]
            url = stream["url"]

            logging.debug(f"Processing stream: {name}")

            # Stream-specific image extraction settings
            stream_image_config = stream.get("image_extraction", {})
            enabled = stream_image_config.get("enabled", global_enabled)
            output_path = stream_image_config.get("output_path", global_output_path)
            width = stream_image_config.get("width", global_width)
            height = stream_image_config.get("height", global_height)
            if stream_image_config:
                logging.debug("Stream-specific image overriding extraction settings: enabled=" + str(enabled) + ", output_path=" + output_path + ", width=" + str(width) + ", height=" + str(height))

            # FFProbe
            ffprobe_details = run_ffprobe(url)

            # Manifest
            manifest_details = None
            if url.endswith(".mpd"):
                manifest_details = parse_mpd_manifest(url)
            else:
                manifest_details = {'not':'available'}

            # Image extraction
            image_file = None
            if enabled:
                image_file = extract_image(url, output_path, name, width, height)

            # Update shared data
            with lock:
                if ffprobe_details:
                    metrics[name] = 1
                    stream_info[name] = {
                        "ffprobe": ffprobe_details,
                        "manifest": manifest_details,
                    }
                    if image_file:
                        latest_images[name] = image_file
                    logging.debug(f"Stream '{name}' updated successfully.")
                else:
                    metrics[name] = 0
                    logging.error(f"Stream '{name}' is down.")

        time.sleep(config["general"].get("frequency", 10))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main HTML page."""
    logging.debug("Serving index page.")

    config = load_config()
    streams = [s["name"] for s in config["streams"]]
    selected = request.query_params.get("stream", streams[0])
    manifest = json.dumps(stream_info.get(selected, {}).get("manifest", {}), indent=2)
    ffprobe = json.dumps(stream_info.get(selected, {}).get("ffprobe", {}), indent=2)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "streams": streams,
        "selected": selected,
        "manifest_details": manifest,
        "ffprobe_details": ffprobe
    })

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    """
    Endpoint to return Prometheus-style metrics with additional stream information.
    """
    logging.debug("Serving metrics endpoint.")
    output = []

    # Fix the stream_up metric format
    for stream_name, value in metrics.items():
        # Change from f"stream_up{{stream=\"{name}\"}}" format
        # to proper "stream_up" metric name with labels
        output.append("# HELP stream_up Stream status (1=up, 0=down)")
        output.append("# TYPE stream_up gauge")
        output.append(f'stream_up{{stream="{stream_name}"}} {value}')

    # Static informational data
    for stream_name, info in stream_info.items():
        ffprobe_data = info.get("ffprobe", {})

        # Track counts for each stream type
        video_streams = []
        audio_streams = []
        
        # Process all streams in the ffprobe data
        for stream in ffprobe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                # Parse frame rate - try avg_frame_rate first, fallback to r_frame_rate
                fps = stream.get("avg_frame_rate", "0/1")
                if fps == "0/0":
                    fps = stream.get("r_frame_rate", "0/1")
                try:
                    fps_num, fps_den = map(int, fps.split("/"))
                    fps_value = fps_num / fps_den if fps_den != 0 else 0
                except (ValueError, ZeroDivisionError):
                    fps_value = 0

                video_info = {
                    "index": stream.get("index", 0),
                    "codec_name": stream.get("codec_name", "unknown"),
                    "bit_rate": stream.get("bit_rate", "0"),
                    "width": stream.get("width", "0"), 
                    "height": stream.get("height", "0"),
                    "fps": fps_value,
                    "profile": stream.get("profile", "unknown"),
                    "pix_fmt": stream.get("pix_fmt", "unknown"),
                    "color_space": stream.get("color_space", "unknown")
                }
                video_streams.append(video_info)

            elif stream.get("codec_type") == "audio":
                audio_info = {
                    "index": stream.get("index", 0),
                    "codec_name": stream.get("codec_name", "unknown"),
                    "bit_rate": stream.get("bit_rate", "0"),
                    "sample_rate": stream.get("sample_rate", "0"),
                    "channels": stream.get("channels", "0"),
                    "profile": stream.get("profile", "unknown"),
                    "channel_layout": stream.get("channel_layout", "unknown")
                }
                audio_streams.append(audio_info)

        # Add stream count metrics
        output.append(f"# HELP stream_video_track_count Number of video tracks in the stream")
        output.append(f"# TYPE stream_video_track_count gauge") 
        output.append(f'stream_video_track_count{{stream="{stream_name}"}} {len(video_streams)}')

        output.append(f"# HELP stream_audio_track_count Number of audio tracks in the stream")
        output.append(f"# TYPE stream_audio_track_count gauge")
        output.append(f'stream_audio_track_count{{stream="{stream_name}"}} {len(audio_streams)}')

        # Add metrics for each video stream
        for i, video in enumerate(video_streams):
            track_id = f"video{video['index']}"
            
            output.append(f"# HELP stream_video_bitrate_bps Video bitrate in bits per second")
            output.append(f"# TYPE stream_video_bitrate_bps gauge")
            output.append(f'stream_video_bitrate_bps{{stream="{stream_name}",track="{track_id}"}} {video["bit_rate"]}')

            output.append(f"# HELP stream_video_fps Video frames per second")
            output.append(f"# TYPE stream_video_fps gauge")
            output.append(f'stream_video_fps{{stream="{stream_name}",track="{track_id}"}} {video["fps"]}')

            output.append(f"# HELP stream_video_resolution_width_pixels Width of the video in pixels")
            output.append(f"# TYPE stream_video_resolution_width_pixels gauge")
            output.append(f'stream_video_resolution_width_pixels{{stream="{stream_name}",track="{track_id}"}} {video["width"]}')

            output.append(f"# HELP stream_video_resolution_height_pixels Height of the video in pixels") 
            output.append(f"# TYPE stream_video_resolution_height_pixels gauge")
            output.append(f'stream_video_resolution_height_pixels{{stream="{stream_name}",track="{track_id}"}} {video["height"]}')

            output.append(f"# HELP stream_video_codec Video codec information")
            output.append(f"# TYPE stream_video_codec untyped")
            output.append(f'stream_video_codec{{stream="{stream_name}",track="{track_id}",codec="{video["codec_name"]}",profile="{video["profile"]}",pixfmt="{video["pix_fmt"]}",colorspace="{video["color_space"]}"}} 1')

        # Add metrics for each audio stream
        for i, audio in enumerate(audio_streams):
            track_id = f"audio{audio['index']}"

            output.append(f"# HELP stream_audio_bitrate_bps Audio bitrate in bits per second")
            output.append(f"# TYPE stream_audio_bitrate_bps gauge")
            output.append(f'stream_audio_bitrate_bps{{stream="{stream_name}",track="{track_id}"}} {audio["bit_rate"]}')

            output.append(f"# HELP stream_audio_sample_rate_hz Audio sample rate in Hz")
            output.append(f"# TYPE stream_audio_sample_rate_hz gauge")
            output.append(f'stream_audio_sample_rate_hz{{stream="{stream_name}",track="{track_id}"}} {audio["sample_rate"]}')

            output.append(f"# HELP stream_audio_channels Number of audio channels")
            output.append(f"# TYPE stream_audio_channels gauge")
            output.append(f'stream_audio_channels{{stream="{stream_name}",track="{track_id}"}} {audio["channels"]}')

            output.append(f"# HELP stream_audio_codec Audio codec information")
            output.append(f"# TYPE stream_audio_codec untyped")
            output.append(f'stream_audio_codec{{stream="{stream_name}",track="{track_id}",codec="{audio["codec_name"]}",profile="{audio["profile"]}",layout="{audio["channel_layout"]}"}} 1')

        # Add general stream information
        format_info = ffprobe_data.get("format", {})
        output.append("# HELP stream_format_name Stream format information")
        output.append("# TYPE stream_format_name untyped")
        output.append(f'stream_format_name{{stream="{stream_name}",format="{format_info.get("format_name", "unknown")}"}} 1')

        output.append("# HELP stream_probe_score FFprobe detection score")
        output.append("# TYPE stream_probe_score gauge")
        output.append(f'stream_probe_score{{stream="{stream_name}"}} {format_info.get("probe_score", 0)}')

        output.append("# HELP stream_start_time Stream start time in seconds")
        output.append("# TYPE stream_start_time gauge")
        output.append(f'stream_start_time{{stream="{stream_name}"}} {format_info.get("start_time", "0")}')

    return PlainTextResponse("\n".join(output))

@app.get("/images/{stream_name}.jpg")
async def image_endpoint(stream_name: str):
    """
    Endpoint to serve the latest extracted image for a specific stream.
    Falls back to testscreen.jpg if no image is found.
    """
    logging.debug(f"Serving image for stream: {stream_name}")
    with lock:
        image_path = latest_images.get(stream_name)

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    if image_path and os.path.exists(image_path):
        return FileResponse(image_path, media_type="image/jpeg", headers=headers)
    
    # Return testscreen.jpg as fallback
    # This code handles fallback image logic when no stream image is available:
    # 1. First tries to get fallback_path from config, defaults to "images/testscreen.jpg"
    # 2. If fallback_path is a URL (starts with http:// or https://):
    #    - Attempts to fetch the image from the URL using requests
    #    - If successful, returns the image content directly
    #    - If fetch fails, logs error and falls back to local image
    # 3. If fallback_path is local or URL fetch failed:
    #    - Checks if the local fallback image exists
    #    - If it exists, serves it as a FileResponse
    # 4. If all fallbacks fail, returns 404 error
    fallback_path = config["image_extraction"].get("fallback_path", "images/testscreen.jpg")
    if fallback_path.startswith(("http://", "https://")):
        try:
            # Fetch the fallback image from the URL using requests
            try:
                response = requests.get(fallback_path)
                response.raise_for_status()
                return Response(content=response.content, media_type="image/jpeg", headers=headers)
            except Exception as e:
                logging.error(f"Failed to fetch remote fallback image from {fallback_path}: {e}")
                # Fall through to use local fallback image
        except Exception as e:
            logging.error(f"Failed to fetch fallback image from URL {fallback_path}: {e}")
            fallback_path = "images/testscreen.jpg"
    if os.path.exists(fallback_path):
        return FileResponse(fallback_path, media_type="image/jpeg", headers=headers)
    
    return Response("No images found", status_code=404)

@app.get("/stream/{stream_name}")
async def stream_image(stream_name: str):
    """
    Stream the latest image for the given stream as a multipart response.
    This really does not scale well since each request blocks a thread.
    """
    async def image_stream():
        while True:
            with lock:
                image_file = latest_images.get(stream_name)

            if not image_file or not os.path.exists(image_file):
                # Send an empty frame if the image is not found
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n\r\n'
                await asyncio.sleep(0.2)  # Adjust FPS to 5 frames per second
                continue

            try:
                with open(image_file, "rb") as f:
                    frame = f.read()
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                    )
                await asyncio.sleep(0.2)  # Adjust FPS to 5 frames per second
            except FileNotFoundError:
                logging.error(f"Image file not found: {image_file}")
            except Exception as e:
                logging.error(f"Error reading image file '{image_file}': {e}")

    # Return the streaming response
    try:
        return StreamingResponse(image_stream(), media_type="multipart/x-mixed-replace; boundary=frame")
    except Exception as e:
        logging.error(f"Error in streaming response for stream: {stream_name}: {e}")
        raise HTTPException(status_code=500, detail="Error in streaming response.")
    
if __name__ == "__main__":
    try:
        config = load_config()
        configure_logging(config["general"].get("log_level", "DEBUG").upper())
        threading.Thread(target=monitor_streams, args=(config,), daemon=True).start()
        uvicorn.run(app, host="0.0.0.0", port=9118, access_log=False)
    except Exception as e:
        logging.critical(f"Service failed to start: {e}")