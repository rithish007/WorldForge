"""Serve only the local voiceover artifacts, with MP4 byte-range support."""

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit

DIRECTORY = Path(__file__).resolve().parents[1] / "artifacts" / "voiceover"
ROUTES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/worldforge-narrated-review.mp4": "worldforge-narrated-review.mp4",
    "/worldforge-narration.wav": "worldforge-narration.wav",
    "/captions-en.vtt": "captions-en.vtt",
    "/short/": "short/index.html",
    "/short/index.html": "short/index.html",
    "/short/worldforge-short-review.mp4": "short/worldforge-short-review.mp4",
    "/short/worldforge-picture-review.mp4": "short/worldforge-picture-review.mp4",
    "/short/captions-en.vtt": "short/captions-en.vtt",
    "/short/narration.mp3": "short/narration.mp3",
}


class ReviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Never expose manifests, downloads, logs or arbitrary artifacts. This
        # map also prevents directory listings and applies equally to GET/HEAD.
        relative = ROUTES.get(urlsplit(path).path)
        return str(DIRECTORY / relative) if relative else str(DIRECTORY / "__not_served__")

    def send_head(self):
        self.byte_range = None
        if urlsplit(self.path).path not in ROUTES:
            self.send_error(404)
            return None
        range_header = self.headers.get("Range")
        if not range_header:
            return super().send_head()
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or not any(match.groups()):
            self.send_error(416, "Unsupported byte range")
            return None
        lower, upper = match.groups()
        start = int(lower) if lower else max(0, size - int(upper))
        end = min(int(upper), size - 1) if upper and lower else size - 1
        if start >= size or end < start:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        stream = path.open("rb")
        stream.seek(start)
        self.byte_range = (start, end)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        return stream

    def copyfile(self, source, outputfile):
        if self.byte_range is None:
            return super().copyfile(source, outputfile)
        remaining = self.byte_range[1] - self.byte_range[0] + 1
        while remaining:
            data = source.read(min(1024 * 1024, remaining))
            if not data:
                break
            outputfile.write(data)
            remaining -= len(data)

    def do_GET(self):
        try:
            super().do_GET()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass  # Browsers cancel an old MP4 range request when seeking.


if __name__ == "__main__":
    handler = functools.partial(ReviewHandler, directory=str(DIRECTORY))
    server = ThreadingHTTPServer(("127.0.0.1", 4175), handler)
    print("Local voiceover review: http://127.0.0.1:4175", flush=True)
    server.serve_forever()
