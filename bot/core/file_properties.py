from pyrogram.types import Message
from typing import Optional, Tuple

def humanbytes(size: int) -> str:
    """Converts bytes into human-readable format."""
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    size_f = float(size)
    while size_f >= 1024 and idx < len(units) - 1:
        size_f /= 1024.0
        idx += 1
    return f"{size_f:.2f} {units[idx]}"

def time_formatter(seconds: float) -> str:
    """Formats seconds into human-readable duration."""
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days > 0:
        return f"{days}d {hours:02d}h {minutes:02d}m {sec:02d}s"
    elif hours > 0:
        return f"{hours:02d}h {minutes:02d}m {sec:02d}s"
    else:
        return f"{minutes:02d}m {sec:02d}s"

def get_media_from_message(message: Message):
    """Extracts media object from a message."""
    if not message:
        return None
    return (
        message.video
        or message.document
        or message.audio
        or message.voice
        or message.video_note
        or message.photo
        or message.animation
    )

def get_file_details(message: Message) -> Tuple[str, int, str, str]:
    """
    Returns (file_name, file_size, mime_type, file_unique_id)
    """
    media = get_media_from_message(message)
    if not media:
        return "unknown_file", 0, "application/octet-stream", ""

    file_size = getattr(media, "file_size", 0)
    unique_id = getattr(media, "file_unique_id", str(message.id))

    # Determine filename
    file_name = getattr(media, "file_name", None)
    if not file_name:
        if message.video:
            file_name = f"video_{message.id}.mp4"
        elif message.audio:
            file_name = f"audio_{message.id}.mp3"
        elif message.voice:
            file_name = f"voice_{message.id}.ogg"
        elif message.photo:
            file_name = f"photo_{message.id}.jpg"
        else:
            file_name = f"file_{message.id}.bin"

    # Determine MIME
    mime_type = getattr(media, "mime_type", None)
    if not mime_type:
        ext = file_name.lower()
        if ext.endswith((".mp4", ".mkv", ".webm", ".avi", ".mov", ".ts", ".m4v")):
            mime_type = "video/mp4"
        elif ext.endswith((".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg")):
            mime_type = "audio/mpeg"
        elif ext.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            mime_type = "image/jpeg"
        else:
            mime_type = "application/octet-stream"

    return file_name, file_size, mime_type, unique_id
