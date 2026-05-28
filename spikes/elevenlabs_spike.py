"""Spike: ElevenLabs eleven-v3 on fal — verify word timestamps, pacing, output shape, vs MiniMax.

The run-0003 problem: a pause-heavy time-list script rendered to 25.5s on MiniMax (31 words). Test a
FLOWING script here and confirm (a) it paces naturally, (b) timestamps=true returns per-word timing.
"""
import os, json, time, subprocess
from dotenv import load_dotenv
load_dotenv()
import fal_client, requests

FLOWING = ("Drop your pup right off the one-oh-one. They'll spend the day on real adventures, "
           "you'll get photos, and pickup is whenever works for you. Carol's Dog Daycare — easy, "
           "friendly, and surprisingly affordable.")
out = "spikes/out"; os.makedirs(out, exist_ok=True)

t0 = time.time()
res = fal_client.subscribe("fal-ai/elevenlabs/tts/eleven-v3", arguments={
    "text": FLOWING, "voice": "Rachel", "stability": 0.5, "speed": 1.0,
    "timestamps": True}, with_logs=False)
ms = int((time.time() - t0) * 1000)
print("keys:", list(res.keys()), "| latency_ms:", ms)
print("words:", len(FLOWING.split()))

# audio
url = res.get("audio", {}).get("url") if isinstance(res.get("audio"), dict) else res.get("audio")
p = f"{out}/eleven.mp3"; open(p, "wb").write(requests.get(url).content)
dur = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of",
                      "default=nw=1:nk=1", p], capture_output=True, text=True).stdout.strip()
print(f"audio duration: {dur}s  (MiniMax did 25.5s for a 31-word time-list; flowing should be far less)")

# timestamps shape
ts = res.get("timestamps")
print("\ntimestamps type:", type(ts).__name__, "| len:", len(ts) if hasattr(ts, "__len__") else "?")
if ts:
    print("first 3 entries:", json.dumps(ts[:3], indent=2)[:500])
    print("last entry:", json.dumps(ts[-1], indent=2)[:200])
