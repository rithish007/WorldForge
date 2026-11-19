"""Assemble the short local demo from an edit decision list and one complete take.

No generation, network calls or publication. Original footage is read only.
Use --analyse to inspect approximate speech alignment before rendering. Explicit
paragraph start/end values override the silence/word-count heuristic. Captions
are a separate VTT file: the player decides whether to enable them.
"""

import argparse
import array
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/voiceover/short"
FPS = 30


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def local_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Inputs must be inside the checkout")
    return path


def validate_config(config, source_duration=None):
    source = local_path(config["source"])
    paragraphs = config.get("paragraphs", config.get("narration", []))
    sections = config.get("sections", [])
    if not paragraphs or len(paragraphs) != len(sections):
        raise ValueError("Every narration paragraph needs one corresponding video section")
    seen = set()
    previous = 0.0
    for paragraph, section in zip(paragraphs, sections):
        ident = paragraph["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", ident) or ident in seen or section["id"] != ident:
            raise ValueError("Paragraph/section IDs must be unique and in matching order")
        seen.add(ident)
        if not paragraph.get("text", "").strip():
            raise ValueError(f"Missing narration text for {ident}")
        start = number(section["start"], f"{ident}.start")
        end = number(section["end"], f"{ident}.end")
        if abs(start - previous) > 0.05 or end <= start:
            raise ValueError("Nominal video sections must be contiguous, positive and start at zero")
        previous = end
        if not section.get("clips"):
            raise ValueError(f"Missing footage for {ident}")
        for clip in section["clips"]:
            clip_in = number(clip["in"], f"{ident}.clip.in")
            clip_out = number(clip["out"], f"{ident}.clip.out")
            speed = number(clip.get("speed", 1), f"{ident}.clip.speed")
            if clip_in < 0 or clip_out <= clip_in or not 0.25 <= speed <= 8:
                raise ValueError(f"Invalid clip interval or speed in {ident}")
            if source_duration is not None and clip_out > source_duration + 0.025:
                raise ValueError(f"Clip exceeds source duration in {ident}")
    declared = number(config.get("duration_seconds", previous), "duration_seconds")
    if abs(declared - previous) > 0.05:
        raise ValueError("duration_seconds must equal the nominal timeline end")
    explicit = ["start" in p or "end" in p for p in paragraphs]
    if any(explicit) and not all("start" in p and "end" in p for p in paragraphs):
        raise ValueError("Supply start and end for every paragraph, or omit all paragraph timings")
    return source, paragraphs, sections


def find_ffmpeg(override):
    if override:
        return str(Path(override).resolve())
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    sys.path.insert(0, str(ROOT / "artifacts/voiceover/tools"))
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Use --ffmpeg or the existing repo-local imageio-ffmpeg installation") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg(executable, arguments, *, level="error", cwd=None):
    result = subprocess.run(
        [executable, "-hide_banner", "-nostdin", "-loglevel", level, "-y", *map(str, arguments)],
        capture_output=True, cwd=cwd,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-10000:])
    return result


def probe(executable, path):
    # The bundled imageio executable has no companion ffprobe. FFmpeg's local
    # input metadata is sufficient for duration, stream presence and dimensions.
    result = subprocess.run([executable, "-hide_banner", "-nostdin", "-i", str(path)], capture_output=True)
    info = result.stderr.decode("utf-8", errors="replace")
    duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
    if not duration:
        raise ValueError(f"Cannot read media duration: {path}")
    seconds = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])
    video_line = next((line for line in info.splitlines() if "Video:" in line), "")
    size = re.search(r"\b(\d{2,5})x(\d{2,5})\b", video_line)
    fps = re.search(r"([\d.]+) fps", video_line)
    return {"duration_seconds": seconds, "has_audio": "Audio:" in info,
            "size": [int(size[1]), int(size[2])] if size else None,
            "fps": float(fps[1]) if fps else None}


def analyse_audio(executable, audio):
    # Decode the entire take. This catches truncated/invalid assets and gives an
    # exact sample duration, unlike a rounded MP3 container duration.
    pcm = ffmpeg(executable, ["-i", audio, "-map", "0:a:0", "-ar", "48000", "-ac", "1", "-f", "s16le", "pipe:1"]).stdout
    samples = array.array("h")
    samples.frombytes(pcm)
    if not samples or max(abs(v) for v in samples) < 100:
        raise ValueError("Narration is empty or contains no audible speech")
    duration = len(samples) / 48000
    del pcm, samples
    result = ffmpeg(executable, ["-i", audio, "-map", "0:a:0", "-af", "silencedetect=noise=-38dB:d=0.18", "-f", "null", "-"], level="info")
    pauses = []
    current = None
    for kind, value in re.findall(r"silence_(start|end):\s*([\d.]+)", result.stderr.decode("utf-8", errors="replace")):
        if kind == "start":
            current = float(value)
        elif current is not None:
            pauses.append([max(0, current), min(duration, float(value))])
            current = None
    if current is not None:
        pauses.append([current, duration])
    trim_start, trim_end = 0.0, duration
    if pauses and pauses[0][0] <= 0.03:
        trim_start = max(0.0, pauses[0][1] - 0.08)
    if pauses and duration - pauses[-1][1] <= 0.03:
        trim_end = min(duration, pauses[-1][0] + 0.15)
    if trim_end <= trim_start:
        raise ValueError("Narration contains no usable speech")
    interior = [[a - trim_start, b - trim_start] for a, b in pauses if a > trim_start and b < trim_end]
    if any(b - a > 5 for a, b in interior):
        raise ValueError("Narration has an interior silent gap longer than five seconds; review the take")
    return duration, trim_start, trim_end, interior


def align(paragraphs, audio_duration, pauses):
    if "start" in paragraphs[0]:
        previous = 0.0
        aligned = []
        for p in paragraphs:
            start = number(p["start"], "paragraph.start")
            end = number(p["end"], "paragraph.end")
            if abs(start - previous) > 0.05 or end <= start:
                raise ValueError("Explicit paragraph timings must be contiguous and begin at zero")
            aligned.append({**p, "start": start, "end": end, "timing_source": "supplied paragraph timing"})
            previous = end
        if abs(previous - audio_duration) > 0.15:
            raise ValueError("Explicit paragraph timings must cover the complete trimmed narration")
        aligned[-1]["end"] = audio_duration
        return aligned
    weights = [len(p["text"].split()) for p in paragraphs]
    total = sum(weights)
    boundaries = [0.0]
    cumulative = 0
    for index, weight in enumerate(weights[:-1]):
        cumulative += weight
        expected = audio_duration * cumulative / total
        candidates = [(a + b) / 2 for a, b in pauses
                      if abs((a + b) / 2 - expected) <= 1.4
                      and (a + b) / 2 > boundaries[-1] + 0.5
                      and (a + b) / 2 < audio_duration - (len(weights) - index - 1) * 0.5]
        boundary = min(candidates, key=lambda t: abs(t - expected)) if candidates else expected
        boundaries.append(boundary)
    boundaries.append(audio_duration)
    return [{**p, "start": boundaries[i], "end": boundaries[i + 1],
             "timing_source": "approximate: word proportion and nearby silence; manual review required"}
            for i, p in enumerate(paragraphs)]


def stamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def captions(paragraphs):
    lines = ["WEBVTT", "", "NOTE Approximate script-based captions; no speech transcription or forced alignment.", ""]
    for paragraph in paragraphs:
        chunks = []
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph["text"].strip()):
            words = sentence.split()
            chunks.extend(" ".join(words[i:i + 11]) for i in range(0, len(words), 11))
        weight = sum(len(chunk.split()) for chunk in chunks)
        cursor = paragraph["start"]
        for chunk in chunks:
            end = cursor + (paragraph["end"] - paragraph["start"]) * len(chunk.split()) / weight
            lines.extend([f"{stamp(cursor)} --> {stamp(end)}", "\n".join(textwrap.wrap(chunk, 46)), ""])
            cursor = end
    return "\n".join(lines)


def normalize_audio(executable, audio, destination, trim_start, trim_end):
    base = f"atrim=start={trim_start:.8f}:end={trim_end:.8f},asetpts=PTS-STARTPTS"
    measured = ffmpeg(executable, ["-i", audio, "-af", base + ",loudnorm=I=-18:TP=-1.5:LRA=7:print_format=json", "-f", "null", "-"], level="info")
    blocks = re.findall(r"\{[^{}]+\}", measured.stderr.decode("utf-8", errors="replace"))
    if not blocks:
        raise RuntimeError("Loudness analysis did not return measurements")
    values = json.loads(blocks[-1])
    for key in ["input_i", "input_tp", "input_lra", "input_thresh", "target_offset"]:
        if not math.isfinite(float(values[key])):
            raise ValueError("Invalid narration loudness measurement")
    norm = ("loudnorm=I=-18:TP=-1.5:LRA=7:linear=true:"
            f"measured_I={values['input_i']}:measured_TP={values['input_tp']}:"
            f"measured_LRA={values['input_lra']}:measured_thresh={values['input_thresh']}:"
            f"offset={values['target_offset']}")
    ffmpeg(executable, ["-i", audio, "-af", base + "," + norm, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", destination])
    return values


def encode_section(executable, source, section, destination, frames):
    arguments = []
    filters = []
    labels = []
    for index, clip in enumerate(section["clips"]):
        arguments.extend(["-ss", f"{clip['in']:.8f}", "-t", f"{clip['out'] - clip['in']:.8f}", "-i", source])
        label = f"v{index}"
        filters.append(f"[{index}:v:0]setpts=(PTS-STARTPTS)/{clip.get('speed', 1):.8f},fps={FPS},setsar=1[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[joined]")
    filters.append(f"[joined]tpad=stop_mode=clone:stop_duration={frames / FPS + 1:.8f},trim=end_frame={frames},setpts=PTS-STARTPTS[out]")
    ffmpeg(executable, [*arguments, "-filter_complex", ";".join(filters), "-map", "[out]", "-an",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                        "-r", str(FPS), "-frames:v", str(frames), destination])


def picture_only(executable, source, source_info, config, paragraphs, sections, allow_trim):
    """Render the approved nominal visual timeline while narration is blocked."""
    duration = sections[-1]["end"]
    if not 60 <= duration <= 90:
        raise ValueError("Picture review must last 60–90 seconds")
    report = {"schema_version": 1, "status": "building_picture", "narration_status": "blocked",
              "duration_seconds": round(duration * FPS) / FPS,
              "source_duration_seconds": source_info["duration_seconds"], "source_size": source_info["size"],
              "fps": FPS, "voice": config.get("voice"), "model_id": config.get("model_id"),
              "output": "worldforge-picture-review.mp4", "captions": None,
              "captions_timing": "Not generated: narration unavailable",
              "paragraphs": [{**p, "start": s["start"], "end": s["end"],
                              "timing_source": "nominal visual section; no generated narration"}
                             for p, s in zip(paragraphs, sections)],
              "sections": [], "warnings": ["Silent picture review only. New narration is blocked; this is not a finished narrated video."],
              "publication_status": "Local artifact only; this tool does not modify or publish the public website.",
              "encoding": {"video": "H.264 CRF16 medium, original resolution, 30fps", "audio": "none"}}
    previous_frame = 0
    for section in sections:
        end_frame = round(section["end"] * FPS)
        frames = end_frame - previous_frame
        if frames <= 0:
            raise ValueError("A picture section has no frames")
        selected = sum((c["out"] - c["in"]) / c.get("speed", 1) for c in section["clips"])
        actual = frames / FPS
        pad, trim = max(0, actual - selected), max(0, selected - actual)
        if pad > 2.01:
            raise ValueError(f"{section['id']} would hold for {pad:.2f}s; shorten its nominal window")
        if trim > 0.5 and not allow_trim:
            raise ValueError(f"{section['id']} would discard {trim:.2f}s of selected footage; shorten its clips")
        report["sections"].append({**section, "start": previous_frame / FPS, "end": end_frame / FPS,
                                   "duration_seconds": actual, "frame_count": frames,
                                   "selected_duration_seconds": selected, "pad_seconds": pad, "trim_seconds": trim})
        previous_frame = end_frame
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="picture-", dir=OUTPUT) as temporary:
        work = Path(temporary)
        paths = []
        for index, section in enumerate(report["sections"]):
            destination = work / f"section-{index:02}.mp4"
            print(f"Encoding picture {section['id']} ({section['duration_seconds']:.2f}s)", flush=True)
            encode_section(executable, source, section, destination, section["frame_count"])
            paths.append(destination)
        listing = work / "concat.txt"
        listing.write_text("\n".join(f"file '{p.name}'" for p in paths), encoding="utf-8")
        assembled = work / "picture.mp4"
        ffmpeg(executable, ["-f", "concat", "-safe", "0", "-i", listing,
                            "-map", "0:v:0", "-an", "-c:v", "copy", "-movflags", "+faststart", assembled])
        final_info = probe(executable, assembled)
        if (final_info["has_audio"] or final_info["size"] != source_info["size"]
                or abs(final_info["duration_seconds"] - report["duration_seconds"]) > 0.08):
            raise RuntimeError("Picture output verification failed; review video was not replaced")
        assembled.replace(OUTPUT / report["output"])
        report["status"] = "picture_ready"
        report["verified_output"] = final_info
    (OUTPUT / "timing-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="docs/demo-short-edit.json")
    parser.add_argument("--audio", help="Override the config's narration_audio path")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--check", action="store_true", help="Validate local inputs without writing artifacts")
    parser.add_argument("--analyse", action="store_true", help="Write timing/captions only, without encoding")
    parser.add_argument("--picture-only", action="store_true", help="Render a clearly labelled silent visual cut using nominal timings")
    parser.add_argument("--allow-video-trim", action="store_true", help="Allow selected footage to be cut short to fit narration")
    args = parser.parse_args()
    report = None
    try:
        config = json.loads(local_path(args.config).read_text(encoding="utf-8-sig"))
        source, paragraphs, sections = validate_config(config)
        executable = find_ffmpeg(args.ffmpeg)
        if not source.is_file():
            raise FileNotFoundError(f"Original recording missing: {source}")
        source_info = probe(executable, source)
        validate_config(config, source_info["duration_seconds"])
        if not source_info["size"] or not source_info["fps"] or abs(source_info["fps"] - FPS) > 0.1:
            raise ValueError("This edit preserves the original 30 fps recording; unexpected source format")
        if args.picture_only:
            if args.check or args.analyse:
                raise ValueError("--picture-only cannot be combined with --check or --analyse")
            report = picture_only(executable, source, source_info, config, paragraphs, sections, args.allow_video_trim)
            print(json.dumps({"status": report["status"], "duration_seconds": report["duration_seconds"],
                              "report": str(OUTPUT / "timing-report.json")}, indent=2))
            return
        audio = local_path(args.audio or config.get("narration_audio", "artifacts/voiceover/short/narration.mp3"))
        if not audio.is_file() or audio.stat().st_size < 1000:
            raise FileNotFoundError("Complete one-take narration is missing; caption-only sections are not permitted")
        raw_duration, trim_start, trim_end, pauses = analyse_audio(executable, audio)
        audio_duration = trim_end - trim_start
        if not 60 <= audio_duration <= 90:
            raise ValueError(f"Narration lasts {audio_duration:.2f}s; review the script/take to fit 60–90 seconds")
        aligned = align(paragraphs, audio_duration, pauses)
        video_duration = math.ceil(audio_duration * FPS) / FPS
        report = {"schema_version": 1, "status": "analysed", "duration_seconds": video_duration,
                  "audio_duration_seconds": audio_duration, "raw_audio_duration_seconds": raw_duration,
                  "audio_trim_start": trim_start, "audio_trim_end": trim_end,
                  "source_duration_seconds": source_info["duration_seconds"], "source_size": source_info["size"],
                  "fps": FPS, "voice": config.get("voice"), "model_id": config.get("model_id"),
                  "captions_timing": "approximate script-based timing; no transcription or forced alignment",
                  "paragraphs": aligned, "sections": [], "warnings": [], "silence_intervals": pauses,
                  "output": "worldforge-short-review.mp4", "captions": "captions-en.vtt",
                  "audio_complete_check": "Entire supplied one-take decoded, speech present, no >5s interior silence. Wording requires listening review.",
                  "encoding": {"video": "H.264 CRF16 medium, original resolution, 30fps", "audio": "AAC 160kbps, two-pass -18LUFS / -1.5dBTP"}}
        trim_issues = []
        previous_frame = 0
        for index, (section, paragraph) in enumerate(zip(sections, aligned)):
            end_frame = math.ceil(audio_duration * FPS) if index == len(sections) - 1 else round(paragraph["end"] * FPS)
            frames = end_frame - previous_frame
            if frames <= 0:
                raise ValueError("A video section has no frames")
            duration = frames / FPS
            selected = sum((clip["out"] - clip["in"]) / clip.get("speed", 1) for clip in section["clips"])
            item = {**section, "start": previous_frame / FPS, "end": end_frame / FPS,
                    "duration_seconds": duration, "frame_count": frames, "selected_duration_seconds": selected,
                    "pad_seconds": max(0, duration - selected), "trim_seconds": max(0, selected - duration)}
            report["sections"].append(item)
            if item["trim_seconds"] > 0.5:
                trim_issues.append(f"{section['id']}: {item['trim_seconds']:.2f}s")
            if item["pad_seconds"] > 2:
                report["warnings"].append(f"{section['id']} holds its final frame for {item['pad_seconds']:.2f}s")
            previous_frame = end_frame
        if trim_issues:
            report["warnings"].append("Footage would be trimmed: " + ", ".join(trim_issues))
        if args.check:
            print(json.dumps(report, indent=2))
            if trim_issues and not args.allow_video_trim:
                raise ValueError("Shorten selected clips or explicitly use --allow-video-trim")
            return
        OUTPUT.mkdir(parents=True, exist_ok=True)
        if trim_issues and not args.allow_video_trim and not args.analyse:
            raise ValueError("Shorten clips after analysing speech timings, or explicitly use --allow-video-trim: " + ", ".join(trim_issues))
        (OUTPUT / "captions-en.vtt").write_text(captions(aligned), encoding="utf-8")
        if not args.analyse:
            with tempfile.TemporaryDirectory(prefix="build-", dir=OUTPUT) as temporary:
                work = Path(temporary)
                wav = work / "normalized.wav"
                report["loudness_input"] = normalize_audio(executable, audio, wav, trim_start, trim_end)
                paths = []
                for index, section in enumerate(report["sections"]):
                    destination = work / f"section-{index:02}.mp4"
                    print(f"Encoding {section['id']} ({section['duration_seconds']:.2f}s)", flush=True)
                    encode_section(executable, source, section, destination, section["frame_count"])
                    paths.append(destination)
                listing = work / "concat.txt"
                listing.write_text("\n".join(f"file '{p.name}'" for p in paths), encoding="utf-8")
                assembled = work / "review.mp4"
                ffmpeg(executable, ["-f", "concat", "-safe", "0", "-i", listing, "-i", wav,
                                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                                    "-af", f"apad,atrim=duration={video_duration:.8f}", "-t", f"{video_duration:.8f}",
                                    "-movflags", "+faststart", assembled])
                final_info = probe(executable, assembled)
                if (not final_info["has_audio"] or final_info["size"] != source_info["size"]
                        or abs(final_info["duration_seconds"] - video_duration) > 0.08):
                    raise RuntimeError("Output verification failed; reviewed video was not replaced")
                assembled.replace(OUTPUT / report["output"])
                report["status"] = "ready"
                report["verified_output"] = final_info
        (OUTPUT / "timing-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "duration_seconds": video_duration,
                          "report": str(OUTPUT / "timing-report.json")}, indent=2))
    except Exception as exc:
        if not args.check:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            failed = {**(report or {}), "schema_version": 1, "status": "failed", "error": str(exc)}
            (OUTPUT / "timing-report.json").write_text(json.dumps(failed, indent=2) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
