"""Spike: MiniMax TTS on fal — confirm endpoint, output shape, and whether per-line timestamps
are obtainable (probe subtitle_enable / output_format). Produces a real voiceover.mp3.
"""
import os, json, time
from dotenv import load_dotenv
load_dotenv()
import fal_client, requests

TEXT = ("Right off the one-oh-one. Drop your pup with people who actually know them. "
        "Carol's Dog Daycare — open seven to seven, walk-ins welcome.")

def call(args, label):
    print(f"\n=== {label} ===")
    try:
        t0 = time.time()
        res = fal_client.subscribe("fal-ai/minimax/speech-02-hd", arguments=args, with_logs=False)
        print(f"  latency={int((time.time()-t0)*1000)}ms  keys={list(res.keys())}")
        print("  raw:", json.dumps(res, indent=2)[:900])
        return res
    except Exception as e:
        print("  FAILED:", repr(e)[:300])
        return None

# baseline call + voice direction params
base = {"text": TEXT, "voice_id": "Wise_Woman", "speed": 1.0, "emotion": "happy",
        "output_format": "url"}
res = call(base, "baseline (voice direction params)")

# probe: does fal accept subtitle_enable and return timecodes?
res_sub = call({**base, "subtitle_enable": True}, "probe subtitle_enable=True")

# save whichever mp3 we got, for the editor audio-mux spike
out_dir = "spikes/out"; os.makedirs(out_dir, exist_ok=True)
pick = res_sub or res
if pick and pick.get("audio", {}).get("url"):
    p = f"{out_dir}/voiceover.mp3"
    open(p, "wb").write(requests.get(pick["audio"]["url"]).content)
    print(f"\nsaved {p} ({os.path.getsize(p)} bytes); duration_ms={pick.get('duration_ms')}")
    print("HAS per-line timestamps in output:",
          any(k for k in pick if k.lower() in ("subtitles", "subtitle", "timestamps", "words")))
