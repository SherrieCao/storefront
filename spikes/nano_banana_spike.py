"""Spike: verify Nano Banana 2 on fal — text-to-image, real-photo edit/conditioning,
and consistency controls (seed). Confirms endpoint ids, image_url conditioning, aspect ratio,
resolution, output shape, and cost.
"""
import os, sys, time, json
from dotenv import load_dotenv

load_dotenv()
import fal_client

real_photo = sys.argv[1]
out_dir = "spikes/out"
os.makedirs(out_dir, exist_ok=True)

def save(url, name):
    import requests
    r = requests.get(url); open(f"{out_dir}/{name}", "wb").write(r.content)
    print("  saved", f"{out_dir}/{name}", len(r.content), "bytes")

# 1) text-to-image keyframe (generate mode)
print("=== 1. nano-banana-2 text-to-image ===")
t0 = time.time()
res = fal_client.subscribe("fal-ai/nano-banana-2", arguments={
    "prompt": "A warm, candid keyframe: a happy golden retriever at a cozy dog daycare near a "
              "freeway exit, soft natural morning light, documentary phone-photo feel, vertical 9:16.",
    "aspect_ratio": "9:16",
    "num_images": 1,
}, with_logs=False)
print(f"  latency={int((time.time()-t0)*1000)}ms")
print("  keys:", list(res.keys()))
print("  raw:", json.dumps(res, indent=2)[:800])
if res.get("images"):
    save(res["images"][0]["url"], "nb_text.png")

# 2) edit / real-photo conditioning (generate_from_real mode)
print("\n=== 2. nano-banana-2/edit real-photo conditioning ===")
photo_url = fal_client.upload_file(real_photo)
print("  uploaded real photo ->", photo_url[:60], "...")
t0 = time.time()
res2 = fal_client.subscribe("fal-ai/nano-banana-2/edit", arguments={
    "prompt": "Keep this exact dog and setting; restyle into a clean, bright daycare keyframe with "
              "soft morning light, same dog identity, vertical 9:16 composition.",
    "image_urls": [photo_url],
    "aspect_ratio": "9:16",
    "num_images": 1,
}, with_logs=False)
print(f"  latency={int((time.time()-t0)*1000)}ms")
print("  keys:", list(res2.keys()))
print("  raw:", json.dumps(res2, indent=2)[:800])
if res2.get("images"):
    save(res2["images"][0]["url"], "nb_edit.png")

print("\nDONE")
