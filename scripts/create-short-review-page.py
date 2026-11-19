"""Build a local-only short demo review page from the public script and timing report.

No network, narration generation or publication. Private download manifests are
deliberately not read. Run again after the encoder writes timing-report.json.
"""

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "voiceover" / "short"


def escape(value):
    return html.escape(str(value), quote=True)


def clock(seconds):
    seconds = max(0, round(float(seconds)))
    return f"{seconds // 60}:{seconds % 60:02}"


def create_page(config_path, report_path, output_directory=OUTPUT):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    output_directory.mkdir(parents=True, exist_ok=True)
    video = output_directory / "worldforge-short-review.mp4"
    ready = report.get("status") == "ready" and video.is_file() and video.stat().st_size > 0
    picture = output_directory / "worldforge-picture-review.mp4"
    picture_ready = report.get("status") == "picture_ready" and picture.is_file() and picture.stat().st_size > 0
    blocked = report.get("status") == "blocked" or report.get("narration_status") == "blocked"
    failed = report.get("status") == "failed" or blocked
    duration = report.get("duration_seconds", config.get("duration_seconds", 0))
    duration_label = clock(duration) + " duration" if ready or picture_ready else "Target: 60–90 seconds"
    voice = config.get("voice", "Daniel")
    if isinstance(voice, dict):
        voice = voice.get("name", "Daniel")
    status = (
        "Ready for your review" if ready else "VISUAL CUT — NARRATION PENDING" if picture_ready
        else "Review blocked" if failed else "Preparing the short review"
    )
    explanation = (
        "Watch the new cut and check the voice, wording and pacing. Captions start off."
        if ready else
        "Review the shorter visual sequence below. This cut is silent: Daniel's new narration is still pending because ElevenLabs has restricted generation on the account. The narration script remains available below."
        if picture_ready else
        "ElevenLabs has restricted narration generation on the account. The complete narrated cut is not ready; the script is available below."
        if blocked else
        "The video could not be completed. The narration script is available below while assembly is checked."
        if failed else
        "The script is available below. The completed video will appear after narration and assembly are verified."
    )
    timings = {paragraph["id"]: paragraph for paragraph in report.get("paragraphs", []) if "id" in paragraph}
    script_rows = []
    for paragraph in config.get("paragraphs", []):
        timing = timings.get(paragraph.get("id"), {})
        stamp = f'<span class="stamp">{clock(timing["start"])}</span>' if ready and "start" in timing else ""
        script_rows.append(f'<li>{stamp}<p>{escape(paragraph.get("text", ""))}</p></li>')
    warnings = report.get("warnings", [])
    warning_markup = "".join(f"<li>{escape(warning)}</li>" for warning in warnings if isinstance(warning, str))
    warning_markup = f'<aside class="notice"><strong>Review notes</strong><ul>{warning_markup}</ul></aside>' if warning_markup else ""
    captions = (output_directory / "captions-en.vtt").is_file()
    track = '<track kind="captions" src="captions-en.vtt" srclang="en" label="English">' if captions else ""
    if ready or picture_ready:
        filename = "worldforge-short-review.mp4" if ready else "worldforge-picture-review.mp4"
        video_label = "Short WorldForge demo narrated by Daniel" if ready else "Silent WorldForge visual cut; narration pending"
        caption_control = f'<label><input id="captions" type="checkbox" {"" if captions else "disabled"}> English captions</label>' if ready else ""
        track = track if ready else ""
        caption_note = "Captions are optional and their phrase timings are approximate." if ready else "Silent visual review only. This is not the completed voiceover video."
        player = f'''<div class="player"><video id="demo" controls playsinline preload="metadata" aria-label="{video_label}"><source src="{filename}" type="video/mp4">{track}Your browser cannot play this video.</video></div>
<div class="player-tools"><button id="restart" type="button">Play from the beginning</button>{caption_control}<a href="{filename}" download>Download {"review" if ready else "silent cut"}</a></div>
<p class="small">{caption_note}</p>'''
    else:
        player = '<div class="pending" role="status">The short narrated video is awaiting completion.</div>'
    audio_link = '<a href="narration.mp3">Listen to original narration take</a>' if ready and (output_directory / "narration.mp3").is_file() else ""
    page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>WorldForge · Short demo review</title>
<style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#101817;color:#e9f2ef}*{box-sizing:border-box}body{margin:0;padding:40px 24px 64px}main{max-width:1120px;margin:auto}a{color:#a7e7c7;text-underline-offset:4px}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:42px}.brand{font-size:21px;font-weight:750;letter-spacing:-.6px}.badge{font-size:12px;text-transform:uppercase;letter-spacing:.12em;border:1px solid #3d6355;border-radius:99px;padding:8px 13px;color:#a7e7c7}h1{font-size:clamp(30px,5vw,48px);letter-spacing:-1.5px;margin:12px 0}p{line-height:1.65}.intro{max-width:720px;color:#afc3bb;margin-bottom:26px}.meta{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}.meta span{background:#1c2b26;border:1px solid #31453c;padding:8px 12px;border-radius:8px;font-size:13px}.player{overflow:hidden;border-radius:16px;border:1px solid #384d44;box-shadow:0 20px 60px #0003;background:#000}video{display:block;width:100%;max-height:74vh}.player-tools{display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-top:18px;font-size:14px}.player-tools label{display:flex;align-items:center;gap:8px}input{accent-color:#8cd4ad}button{cursor:pointer;border:0;border-radius:9px;padding:12px 17px;background:#a7e7c7;color:#10271b;font:inherit;font-weight:650}button:hover{background:#c1f5da}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #a7e7c7;outline-offset:5px}.small,footer{font-size:13px;color:#92aaa0}.notice,.pending{background:#202b24;border:1px solid #536548;border-radius:12px;padding:20px 24px;margin:24px 0}.pending{min-height:230px;display:grid;place-items:center;text-align:center}.notice ul{padding-left:20px}.notice li{line-height:1.6}details{border:1px solid #32473d;border-radius:12px;margin:32px 0;padding:18px 22px}summary{cursor:pointer;font-weight:650}ol{list-style:none;padding:0}li p{margin:5px 0 20px}li:last-child p{margin-bottom:0}.stamp{font:12px ui-monospace,monospace;color:#a7e7c7}footer{border-top:1px solid #2c4036;padding-top:22px;display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap}@media(max-width:600px){body{padding:24px 15px 40px}header{margin-bottom:28px}.player-tools{gap:14px}h1{letter-spacing:-.8px}}
</style></head><body><main>
<header><span class="brand">WorldForge</span><span class="badge">Local review only</span></header>
<h1>Short demo, clearer story.</h1><p class="intro">__EXPLANATION__</p>
<div class="meta"><span>__STATUS__</span><span id="duration">__DURATION__</span><span>__VOICE_STATUS__</span></div>
__PLAYER____WARNINGS__
<details><summary>Narration script</summary><p class="small">This script is for local review. It will not appear on the live website.</p><ol>__SCRIPT__</ol>__AUDIO__</details>
<footer><span>The public WorldForge website is unchanged.</span><a href="/">Previous full-length review</a></footer>
</main><script>
const video=document.getElementById('demo');
const captionChoice=document.getElementById('captions');
if(video){
 const syncCaptions=()=>{for(const track of video.textTracks)track.mode=captionChoice?.checked?'showing':'disabled';};
 if(captionChoice)captionChoice.checked=false;
 syncCaptions();
 video.textTracks.addEventListener('addtrack',syncCaptions);
 video.addEventListener('loadedmetadata',()=>{syncCaptions();const seconds=Math.round(video.duration);if(Number.isFinite(seconds))document.getElementById('duration').textContent=Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0')+' duration';});
 captionChoice?.addEventListener('change',syncCaptions);
 document.getElementById('restart').addEventListener('click',()=>{video.currentTime=0;video.play().catch(()=>{});});
}
</script></body></html>'''
    replacements = {
        "__EXPLANATION__": escape(explanation), "__STATUS__": escape(status),
        "__DURATION__": escape(duration_label),
        "__VOICE_STATUS__": escape(voice + " · British English" if ready else "Planned voice: " + voice),
        "__PLAYER__": player, "__WARNINGS__": warning_markup,
        "__SCRIPT__": "".join(script_rows), "__AUDIO__": audio_link,
    }
    for token, value in replacements.items():
        page = page.replace(token, value)
    destination = output_directory / "index.html"
    destination.write_text(page, encoding="utf-8")
    print(f"Local short review page: {destination}")
    print(f"Status: {status}; duration: {clock(duration)}")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "docs" / "demo-short-edit.json")
    parser.add_argument("--report", type=Path, default=OUTPUT / "timing-report.json")
    arguments = parser.parse_args()
    create_page(arguments.config, arguments.report)
