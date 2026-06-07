"""Settings and stream URL management."""
from pathlib import Path
import json

CONFIG_FILE = Path(__file__).parent.parent / 'camera_config.json'


def load_config():
    """Load camera stream configuration."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'phone_stream_url': 'http://192.168.1.50:8080/video',
        'stream_timeout': 10,
        'frame_scale': 0.5,
    }


def save_config(config):
    """Save camera stream configuration."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
