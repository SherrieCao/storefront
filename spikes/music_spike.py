"""Spike: Beatoven music-gen on fal + librosa beat detection.
Generate a short mood-matched instrumental, then extract the beat grid for beat-synced cutting.
"""
import os, json, time, subprocess
from dotenv import load_dotenv
load_dotenv()
import fal_client, requests

out = "spikes/out"; os.makedirs(out, exist_ok=True)
t0 = time.time()
res = fal_client.subscribe("beatoven/music-generation", arguments={
    "prompt": "upbeat warm acoustic indie pop, bright and playful, social media ad energy, light percussion",
    "duration": 16}, with_logs=False)
print("latency_ms:", int((time.time() - t0) * 1000), "| keys:", list(res.keys()))
print("raw:", json.dumps(res, default=str)[:500])

audio = res.get("audio")
url = audio.get("url") if isinstance(audio, dict) else (audio if isinstance(audio, str) else res.get("audio_url"))
mp3 = f"{out}/music.mp3"; open(mp3, "wb").write(requests.get(url).content)
dur = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",mp3],
                     capture_output=True, text=True).stdout.strip()
print("music saved:", mp3, "| duration:", dur, "s")

# beat detection — convert to wav for a reliable librosa backend, then beat_track
wav = f"{out}/music.wav"
subprocess.run(["ffmpeg","-y","-i",mp3,"-ar","22050","-ac","1",wav], capture_output=True)
import librosa
y, sr = librosa.load(wav, sr=22050)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
times = librosa.frames_to_time(beats, sr=sr)
print(f"\nBPM: {float(tempo):.1f} | {len(times)} beats")
print("beat times (s):", [round(float(t),2) for t in times[:16]])
print("avg beat interval:", round(float(times[-1]-times[0])/max(1,len(times)-1),3), "s")
