from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


def resolve_ffmpeg_binary() -> str:
    ffmpeg_bin = (os.getenv('IMAGEIO_FFMPEG_EXE') or '').strip() or shutil.which('ffmpeg')
    if ffmpeg_bin:
        return ffmpeg_bin
    try:
        import imageio_ffmpeg

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_bin = ''
    return (ffmpeg_bin or '').strip()


def poster_bytes_from_video_file(*, source_bytes: bytes, source_ext: str) -> bytes:
    input_path = ''
    output_path = ''
    ffmpeg_bin = resolve_ffmpeg_binary()
    if not ffmpeg_bin:
        return b''

    ext = source_ext if source_ext.startswith('.') else f'.{source_ext}'
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext or '.mp4') as in_tmp:
            in_tmp.write(source_bytes)
            input_path = in_tmp.name
        fd, output_path = tempfile.mkstemp(suffix='.jpg')
        os.close(fd)
        cmd = [
            ffmpeg_bin,
            '-y',
            '-ss',
            '00:00:00.20',
            '-i',
            input_path,
            '-frames:v',
            '1',
            '-q:v',
            '4',
            '-vf',
            'scale=960:-2:force_original_aspect_ratio=decrease',
            output_path,
        ]
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(output_path, 'rb') as out_fh:
            return out_fh.read()
    except Exception:
        return b''
    finally:
        if input_path and os.path.exists(input_path):
            os.remove(input_path)
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
