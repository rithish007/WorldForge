"""Add reviewed action pauses to one existing take; never generates speech.

Insertion positions refer to the original decoded take. Speech samples are
unchanged, and insertion points must fall inside quiet audio. Run --captions-only
after assembly to map approximate script captions around the added pauses.
"""

import argparse
import array
import importlib.util
import json
import math
from pathlib import Path
import re
import wave

ROOT = Path(__file__).resolve().parents[1]
RATE = 48000
spec = importlib.util.spec_from_file_location("demo_builder", ROOT / "scripts/build-short-demo.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captions-only", action="store_true")
    args = parser.parse_args()
    config_path = ROOT / "docs/demo-short-edit.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    timing = config["audio_edit"]
    boundaries = timing["source_paragraph_boundaries"]
    insertions = timing["pause_inserts"]
    source_end = round(boundaries[-1] * RATE)
    positions = [(round(item["at"] * RATE), round(item["seconds"] * RATE)) for item in insertions]
    if any(pos <= 0 or pos >= source_end or count <= 0 for pos, count in positions):
        raise ValueError("Invalid source pause insertion")
    if positions != sorted(positions) or len(set(pos for pos, _ in positions)) != len(positions):
        raise ValueError("Insertions must be unique and ordered")

    def mapped(seconds):
        sample = round(seconds * RATE)
        return (sample + sum(count for pos, count in positions if pos <= sample)) / RATE

    if args.captions_only:
        original = [{**p, "start": boundaries[i], "end": boundaries[i + 1]}
                    for i, p in enumerate(config["paragraphs"])]
        captions = builder.captions(original)

        def replace(match):
            h, m, s = match.group().split(":")
            return builder.stamp(mapped(int(h) * 3600 + int(m) * 60 + float(s)))

        captions = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3}", replace, captions)
        (builder.OUTPUT / "captions-en.vtt").write_text(captions, encoding="utf-8")
        print("Mapped approximate captions around offline action pauses")
        return

    executable = builder.find_ffmpeg(None)
    raw = builder.ffmpeg(executable, ["-i", builder.local_path(timing["source"]),
        "-map", "0:a:0", "-ar", str(RATE), "-ac", "1", "-f", "s16le", "pipe:1"]).stdout
    samples = array.array("h")
    samples.frombytes(raw)
    if len(samples) < source_end:
        raise ValueError("Original take ends before the reviewed final boundary")
    for pos, _ in positions:
        window = samples[pos - 960:pos + 960]
        rms = math.sqrt(sum(v * v for v in window) / len(window))
        if rms > 420:
            raise ValueError(f"Insertion at {pos / RATE:.3f}s would cut audible speech: RMS {rms:.1f}")
    destination = builder.local_path(config["narration_audio"])
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        cursor = 0
        for pos, count in positions:
            output.writeframes(samples[cursor:pos].tobytes())
            output.writeframes(b"\0\0" * count)
            cursor = pos
        output.writeframes(samples[cursor:source_end].tobytes())
    for i, (paragraph, section) in enumerate(zip(config["paragraphs"], config["sections"])):
        paragraph["start"] = section["start"] = mapped(boundaries[i])
        paragraph["end"] = section["end"] = mapped(boundaries[i + 1])
    config["duration_seconds"] = mapped(boundaries[-1])
    builder.analyse_audio(executable, destination)  # rejects empty audio or >5s interior gaps
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"timed_audio": str(destination), "duration_seconds": config["duration_seconds"],
                      "added_pause_seconds": sum(count for _, count in positions) / RATE,
                      "speech": "Original speech samples preserved; no synthesis or time stretching"}))


if __name__ == "__main__":
    main()
