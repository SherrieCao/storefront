"""Diagnostic: CassetteAI music-generator (instrumental bed) + librosa beat detection."""
import os, time, json, subprocess
from dotenv import load_dotenv
load_dotenv()
import fal_client, requests

out = "spikes/out"; os.makedirs(out, exist_ok=True)
t0 = time.time()
res = fal_client.subscribe("cassetteai/music-generator", arguments={
    "prompt": "upbeat warm acoustic indie pop, bright and playful, social media ad energy, light percussion, no vocals",
    "duration": 16}, with_logs=False)
print("latency_ms:", int((time.time() - t0) * 1000), "| keys:", list(res.keys()), flush=True)
print("raw:", json.dumps(res, default=str)[:500], flush=True)

af = res.get("audio_file") or res.get("audio")
url = af.get("url") if isinstance(af, dict) else (af if isinstance(af, str) else res.get("audio_url"))
ext = ".wav" if ".wav" in (url or "") else ".mp3"
src = f"{out}/music{ext}"; open(src, "wb").write(requests.get(url).content)
dur = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",src],
                     capture_output=True, text=True).stdout.strip()
print("music saved:", src, "| duration:", dur, "s", flush=True)

wav = f"{out}/music_22k.wav"
subprocess.run(["ffmpeg","-y","-i",src,"-ar","22050","-ac","1",wav], capture_output=True)
import librosa
y, sr = librosa.load(wav, sr=22050)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
times = librosa.frames_to_time(beats, sr=sr)
print(f"BPM: {float(tempo):.1f} | {len(times)} beats", flush=True)
print("beat times (s):", [round(float(t),2) for t in times[:16]], flush=True)
print("avg beat interval:", round(float(times[-1]-times[0])/max(1,len(times)-1),3), "s", flush=True)
