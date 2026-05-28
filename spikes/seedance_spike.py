"""Spike: per-shot Seedance 2.0 image-to-video with a keyframe start frame + generate_audio=False.
Confirms the central shot-loop mechanic: keyframe -> single-shot silent clip. Verifies the clip
has NO audio stream when generate_audio=False. Uses fast tier / 480p / 4s to minimize cost.
"""
import os, sys, time, json, subprocess
from dotenv import load_dotenv

load_dotenv()
import fal_client, requests

keyframe = sys.argv[1]  # local png start frame
out_dir = "spikes/out"; os.makedirs(out_dir, exist_ok=True)

img_url = fal_client.upload_file(keyframe)
print("keyframe uploaded:", img_url[:60], "...")

t0 = time.time()
res = fal_client.subscribe("bytedance/seedance-2.0/fast/image-to-video", arguments={
    "image_url": img_url,
    "prompt": "Slow gentle push-in on the dog; soft natural morning light; subtle ambient motion. "
              "One continuous shot, no cuts.",
    "resolution": "480p",
    "duration": "4",
    "aspect_ratio": "9:16",
    "generate_audio": False,
}, with_logs=True)
print(f"latency={int((time.time()-t0)*1000)}ms")
print("keys:", list(res.keys()))
print("raw:", json.dumps(res, indent=2)[:600])

url = res["video"]["url"]
path = f"{out_dir}/seedance_shot.mp4"
open(path, "wb").write(requests.get(url).content)
print("saved", path, os.path.getsize(path), "bytes")

# verify NO audio stream
probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
streams = probe.stdout.split()
print("streams:", streams, "-> audio present:", "audio" in streams)
dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=noprint_wrappers=1:nokey=1", path],
                     capture_output=True, text=True).stdout.strip()
print("duration_s:", dur)
