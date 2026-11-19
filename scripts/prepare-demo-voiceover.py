"""Assemble an ElevenLabs narration for local review; never publish anything.

Install imageio-ffmpeg==0.6.0 into artifacts/voiceover/tools first.
The ignored download manifest contains expiring asset URLs from ElevenLabs.
"""

import argparse
import array
import concurrent.futures
import html
import json
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "voiceover"
sys.path.insert(0, str(OUTPUT / "tools"))
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RATE = 48000


def run(arguments, capture=False):
    return subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True, capture_output=capture,
    )


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def download(item):
    destination = audio_path(item)
    if not destination.exists():
        url = item["content_url"]
        if not url.startswith("https://storage.googleapis.com/"):
            raise ValueError("Unexpected ElevenLabs audio asset origin")
        with urllib.request.urlopen(url, timeout=60) as response:
            destination.write_bytes(response.read())
    if destination.stat().st_size < 1000:
        raise ValueError(f"Audio asset is empty: {item['id']}")
    return item["id"]


def audio_path(item):
    # A different voice/take must never silently reuse an earlier audio file.
    generation_id = item["generation_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", generation_id):
        raise ValueError("Invalid audio generation ID")
    return OUTPUT / f"{item['id']}-{generation_id}.mp3"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--manifest", default="download-manifest.json")
    parser.add_argument("--allow-missing", action="store_true", help="Make a clearly labelled incomplete review draft")
    args = parser.parse_args()
    script = json.loads((ROOT / "docs/demo-narration.json").read_text(encoding="utf-8"))
    manifest_path = (OUTPUT / args.manifest).resolve()
    if manifest_path.parent != OUTPUT.resolve():
        raise ValueError("Manifest must be a local voiceover artifact")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["voice"] != script["voice"]:
        raise ValueError("Manifest voice must match the selected script voice")
    assets = {item["id"]: item for item in manifest["segments"]}
    missing = [s["id"] for s in script["segments"] if assets[s["id"]]["status"] != "completed"]
    if missing and not args.allow_missing:
        raise RuntimeError(f"Narration incomplete: {', '.join(missing)}. Use --allow-missing for a review draft only.")
    if args.download:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for segment_id in pool.map(download, [a for a in assets.values() if a["status"] == "completed"]):
                print(f"Downloaded {segment_id}")

    timeline = array.array("h", [0]) * round(RATE * script["duration_seconds"])
    cues = ["WEBVTT", ""]
    report = []
    for segment in script["segments"]:
        start, end = segment["start"], segment["end"]
        asset = assets[segment["id"]]
        available = asset["status"] == "completed"
        duration = end - start
        speed = 1.0
        if available:
            duration = asset["duration_secs"]
            speed = max(1.0, duration / (end - start - 0.05))
            if speed > 1.12:
                raise RuntimeError(f"Narration needs a timing review: {segment['id']}")
            audio = run([
                "-i", str(audio_path(asset)),
                "-af", f"atempo={speed:.6f},loudnorm=I=-18:TP=-1.5:LRA=7",
                "-ar", str(RATE), "-ac", "1", "-f", "s16le", "pipe:1",
            ], capture=True).stdout
            samples = array.array("h")
            samples.frombytes(audio)
            duration = len(samples) / RATE
            offset = round(start * RATE)
            if offset + len(samples) > round(end * RATE):
                raise RuntimeError(f"Audio exceeds segment window: {segment['id']}")
            if any(timeline[offset:offset + len(samples)]):
                raise RuntimeError("Narration segments overlap")
            timeline[offset:offset + len(samples)] = samples
        report.append({"id": segment["id"], "start": start, "audio_end": start + duration, "window_end": end, "status": "ready" if available else "audio missing", "speed": speed})
        # Draft captions follow phrase lengths within the actual audio window.
        # They are approximate, not a claimed forced-alignment transcript.
        phrases = re.split(r"(?<=[.!?])\s+", segment["text"])
        chunks = []
        for phrase in phrases:
            words = phrase.split()
            for index in range(0, len(words), 12):
                chunks.append(" ".join(words[index:index + 12]))
        total_words = sum(len(chunk.split()) for chunk in chunks)
        cue_start = start
        for chunk in chunks:
            cue_end = cue_start + duration * len(chunk.split()) / total_words
            lines = textwrap.wrap(chunk, width=46)
            cues.extend([f"{timestamp(cue_start)} --> {timestamp(cue_end)}", "\n".join(lines), ""])
            cue_start = cue_end

    wav_path = OUTPUT / "worldforge-narration.wav"
    with wave.open(str(wav_path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(timeline.tobytes())
    (OUTPUT / "captions-en.vtt").write_text("\n".join(cues), encoding="utf-8")
    (OUTPUT / "timing-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    run(["-i", str(ROOT / script["source"]), "-i", str(wav_path),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-t", str(script["duration_seconds"]), "-movflags", "+faststart",
         str(OUTPUT / "worldforge-narrated-review.mp4")])
    rows = "".join(
        f'<tr><td><button type="button" data-time="{s["start"]}">{timestamp(s["start"])}</button></td>'
        f'<td>{html.escape(s["text"])}</td><td>{html.escape(r["status"])}</td></tr>'
        for s, r in zip(script["segments"], report)
    )
    missing_windows = ", ".join(
        f"{timestamp(s['start'])}–{timestamp(s['end'])}"
        for s in script["segments"] if s["id"] in missing
    )
    warning = (
        f"<strong>Incomplete review draft.</strong> Narration at {missing_windows} is awaiting ElevenLabs audio. "
        f"That section currently has captions only. {len(report) - len(missing)} other sections have generated speech."
        if missing else "Complete local review draft."
    )
    page = """<!doctype html><html lang="en-GB"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>WorldForge — Local voiceover review</title>
<style>body{font:17px/1.55 system-ui;background:#f6f5f1;color:#252821;margin:0;padding:32px}main{max-width:1200px;margin:auto}h1{font-size:32px;margin-bottom:8px}p{max-width:85ch}video{width:100%;max-height:72vh;background:#151515;border-radius:12px}aside{padding:16px 20px;background:#fff1cf;border:1px solid #c9a953;border-radius:8px;margin:20px 0}table{border-collapse:collapse;width:100%;background:white}td,th{padding:14px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top}td:first-child{white-space:nowrap}button,a{color:#36592e}button{cursor:pointer;padding:7px;background:#edf2e8;border:1px solid #a7b7a0;border-radius:5px}small{color:#5a6255}video::cue{font:19px/1.4 sans-serif}</style>
<main><h1>WorldForge voiceover review</h1><p>NARRATOR · British English · ElevenLabs Multilingual v2 · 2 minutes 37 seconds</p>
<aside>WARNING</aside><p><strong>Local review only.</strong> The live website has not been changed. Review the wording, pronunciation and timing below. Caption timing is approximate.</p>
<video controls playsinline preload="metadata" aria-label="WorldForge demo with draft British narration"><source src="worldforge-narrated-review.mp4" type="video/mp4"><track src="captions-en.vtt" kind="captions" srclang="en-GB" label="English" default></video>
<p><button type="button" data-time="1">Play from the beginning</button> · <a href="worldforge-narrated-review.mp4" download>Download review MP4</a> · <a href="worldforge-narration.wav" download>Download narration WAV</a></p>
<h2>Timed script</h2><small>Select a timestamp to play that section.</small><table><thead><tr><th>Start</th><th>Narration</th><th>Status</th></tr></thead><tbody>ROWS</tbody></table>
<script>const video=document.querySelector('video');document.querySelectorAll('[data-time]').forEach(button=>button.addEventListener('click',()=>{video.currentTime=Number(button.dataset.time);video.play();video.scrollIntoView({behavior:'smooth',block:'center'});}));</script></main></html>"""
    page = page.replace("NARRATOR", html.escape(script["voice"]))
    (OUTPUT / "index.html").write_text(page.replace("WARNING", warning).replace("ROWS", rows), encoding="utf-8")
    print(json.dumps({"review": str(OUTPUT / "index.html"), "missing": missing, "ready_segments": len(report) - len(missing)}, indent=2))


if __name__ == "__main__":
    main()
