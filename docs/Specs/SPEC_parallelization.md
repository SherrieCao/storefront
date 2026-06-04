# Spec — Pipeline Parallelization (cut processing time ~30-40%)

> Current: ~10 minutes per run, strictly sequential after the Director. Four stages wait behind
> dependencies they don't actually have. This spec introduces parallel execution where the
> dependency graph allows, without changing any stage's logic or output.
>
> Estimated savings: ~2-4 minutes depending on asset count and retry frequency.
> Risk: low — each stage's inputs/outputs are unchanged; only the orchestration in run.py changes.

## Before you start
Read `run.py` (the orchestrator), plus these four files to understand their actual dependencies:
- `pipeline/shots.py` — already uses `ThreadPoolExecutor` with `MAX_SHOT_CONCURRENCY`
- `pipeline/keyframes.py` — currently a sequential `for seg in need:` loop
- `pipeline/enhance.py` — signature: `enhance_assets(run, inventory)` — no brief dependency
- `pipeline/music.py` — signature: `run_music(run, brief)` — no shots/keyframes dependency

Also read `pipeline/budget.py` (cost ceiling checks must remain thread-safe) and `pipeline/tracing.py`
(logging must be thread-safe — verify `run.log()` and `run.trace()` don't race).

---

## The confirmed dependency graph

```
                                              ┌→ keyframes (concurrent) → shots (already concurrent) ─┐
triage → concept⟳ → director⟳ → [gate] ──────┤                                                       ├→ plan_timeline → voice → render → review
                                              └→ music ───────────────────────────────────────────────┘
         └→ enhance (parallel with concept+director) ──→ (done before keyframes need it)
```

Four changes, in priority order:

---

## Change 1 — Enhance runs parallel with concept+director (biggest easy win)

### The problem
`enhance_assets(run, inventory)` depends ONLY on `inventory` (from triage). It currently runs
AFTER concept + director, waiting ~60-180s behind LLM calls + critic loops it doesn't need.

### The fix
Start enhance immediately after triage, in a background thread. It runs while concept and
director think. By the time the director finishes and keyframes need the enhanced photos,
enhance is already done (enhance typically takes ~15-45s; concept+director takes ~60-180s).

In `run.py`, after triage:
```python
from concurrent.futures import ThreadPoolExecutor, Future

# Start enhance in background immediately after triage (it only needs inventory)
with ThreadPoolExecutor(max_workers=1) as bg:
    enhance_future: Future = bg.submit(enh.enhance_assets, run, inventory)

    # Meanwhile, concept + director run sequentially (they depend on each other)
    concept = concept_.run_concept(run, inventory, use_cache=cached("concept"))
    brief = dir_.run_director(run, inventory, concept, use_cache=cached("director"))
    # ... escalation logic ...
    # ... approval gate ...

    # Now collect enhance result (almost certainly done by now)
    enhance_future.result()  # blocks if somehow still running; raises if it failed
```

When `use_cache` is true for enhance, the background thread returns immediately from cache.

### Savings: ~15-45s (the entire enhance duration, hidden behind LLM thinking time)

---

## Change 2 — Keyframes run concurrently (the biggest single bottleneck fix)

### The problem
`keyframes.py` generates frames in a sequential `for seg in need:` loop. With 4-6 keyframes
each taking ~10-15s on fal, that's ~40-90s sequential. Shots already proved that
`ThreadPoolExecutor` works for concurrent fal calls with a budget lock.

### The fix
Mirror the pattern from `shots.py`: use `ThreadPoolExecutor` with a concurrency cap and a
budget-check lock. Replace the `for seg in need:` loop with:

```python
import threading
from concurrent.futures import ThreadPoolExecutor

lock = threading.Lock()

def do_keyframe(seg):
    n = seg.get("n")
    dst = out_dir / f"kf_{n}.png"
    # ... existing per-segment logic (mode selection, prompt building, _make_keyframe call) ...
    # Budget check under the lock (same pattern as shots.py):
    with lock:
        budget.check_ceiling(run, budget.keyframe_image(1), f"keyframes[{n}]")
    _make_keyframe(run, mode, prompt, image_urls, str(dst), seed + n)  # vary seed per frame
    with lock:
        kf_map[str(n)] = {"path": str(dst), "mode": mode, "segment_type": seg["type"]}
    run.log(f"Keyframes: segment {n} [{mode}] -> {dst.name}")

workers = min(config.MAX_KEYFRAME_CONCURRENCY, len(need))  # new config constant
with ThreadPoolExecutor(max_workers=workers) as ex:
    list(ex.map(do_keyframe, need))
```

Add `MAX_KEYFRAME_CONCURRENCY = 4` to `config.py` (fal can handle 4 concurrent Nano Banana
calls; tune if rate-limited).

**Seed handling:** currently `seed` is per-run; with concurrent keyframes, each must get a
distinct seed. Use `seed + n` (segment number) instead of a shared `seed` — deterministic and
distinct. The `seed + attempt * 1009` retry logic inside `_make_keyframe` still works on top.

**The `preserve_before` early-return:** keep it — that path skips fal entirely (just copies a
file) and should work fine inside the thread.

### Savings: ~30-60s (N keyframes in parallel instead of sequential)

---

## Change 3 — Music runs parallel with keyframes+shots

### The problem
`run_music(run, brief)` depends only on the brief's mood/pacing. It currently runs AFTER
shots, waiting behind the entire keyframe+shot generation pipeline (~3-5 min) for no reason.

### The fix
Start music as soon as the director finishes, running in parallel with keyframes and shots.
In `run.py`:

```python
# After the approval gate, before keyframes:
music_future = bg.submit(music_.run_music, run, brief)

# keyframes + shots run (these are the slow ones)
keyframes = kf_.run_keyframes(run, brief, inventory, use_cache=cached("keyframes"))
shots = shots_.run_shots(run, brief, inventory, keyframes, use_cache=cached("shots"))

# Collect music (almost certainly done — it's fast)
music = music_future.result()
```

When `use_cache` is true for music, it returns immediately from cache.

### Savings: ~10-20s (music selection + librosa beat grid, hidden behind generation)

---

## Change 4 — Pipelined keyframes→shots (aggressive, optional)

### The problem
Currently: ALL keyframes finish → THEN all shots start. But if shot 1's keyframe is ready,
shot 1's Seedance generation could start while keyframes 2-6 are still being produced.

### The fix (more complex — build only if Changes 1-3 aren't enough)
Use a per-shot `threading.Event` or a `queue.Queue` to signal each shot's keyframe readiness:

```python
from queue import Queue
import threading

kf_ready = {}  # n -> threading.Event
for seg in seedance_segs:
    kf_ready[seg["n"]] = threading.Event()

def do_keyframe(seg):
    # ... generate keyframe ...
    kf_ready[seg["n"]].set()  # signal: this shot's keyframe is ready

def do_shot(seg):
    kf_ready[seg["n"]].wait()  # block until MY keyframe is done
    # ... existing shot generation + judge + retry loop ...

with ThreadPoolExecutor(max_workers=config.MAX_KEYFRAME_CONCURRENCY) as kf_ex:
    kf_ex.map(do_keyframe, keyframe_segs)
    # Shots start as keyframes become available:
    with ThreadPoolExecutor(max_workers=config.MAX_SHOT_CONCURRENCY) as shot_ex:
        shot_ex.map(do_shot, seedance_segs)
```

This overlaps the keyframe and shot generation phases. A 4-shot ad where each keyframe takes
15s and each shot takes 120s would go from (4×15 + max(4×120/concurrency)) to just
(max(4×120/concurrency) + 15) — the keyframes are hidden behind shot generation.

### Savings: ~15-60s (the entire keyframe phase hidden behind shot generation)
### Complexity: Medium — requires the Event-based signaling and careful error propagation
### Recommendation: build Changes 1-3 first, measure, and only add this if you need more.

---

## Thread safety audit (verify before shipping)

These must be safe for concurrent access:
- **`run.log()`** — appends to a file + prints. Check: is the file handle shared? Add a lock
  if not already thread-safe (a single `threading.Lock` on write is fine).
- **`run.trace()`** — appends JSON lines to `trace.jsonl`. Same file-handle concern.
- **`run.add_cost()`** — mutates `run.costs` dict. Must be under a lock. Check if `budget.py`
  already serializes this (shots.py uses a lock for its budget checks — extend it).
- **`run.reason()`** — appends to `REASONING.md`. Same pattern as log/trace.

The simplest fix: a single `threading.RLock` on the `Run` object, acquired by `log()`,
`trace()`, `add_cost()`, and `reason()`. Shots.py already has its own lock for budget checks;
unify or nest carefully. Verify no deadlock risk.

---

## Config additions
```python
MAX_KEYFRAME_CONCURRENCY = 4   # concurrent Nano Banana calls (tune if rate-limited)
# MAX_SHOT_CONCURRENCY already exists
```

---

## run.py restructured flow (Changes 1-3 applied)

```python
# Phase 1: sequential (each depends on the previous)
inventory = tri.run_triage(run, input_dir, use_cache=cached("triage"))

# Phase 2: enhance in background; concept + director sequential in foreground
with ThreadPoolExecutor(max_workers=2) as bg:
    enhance_future = bg.submit(enh.enhance_assets, run, inventory, use_cache=cached("enhance"))
    
    concept = concept_.run_concept(run, inventory, use_cache=cached("concept"))
    brief = dir_.run_director(run, inventory, concept, use_cache=cached("director"))
    # ... escalation + creative flags + approval gate ...
    
    enhance_future.result()  # collect (should be done by now)
    
    # Phase 3: music in background; keyframes + shots in foreground
    music_future = bg.submit(music_.run_music, run, brief, use_cache=cached("music"))
    
    keyframes = kf_.run_keyframes(run, brief, inventory, use_cache=cached("keyframes"))  # now concurrent internally
    shots = shots_.run_shots(run, brief, inventory, keyframes, use_cache=cached("shots"))  # already concurrent
    
    music = music_future.result()  # collect

# Phase 4: sequential (each depends on the previous)
timeline = ed_.plan_timeline(run, brief, shots, keyframes, inventory, beats=music.get("beats"))
voice = voice_.run_voice(run, brief, timeline, inventory, use_cache=cached("voice"))
final = ed_.render(run, timeline, voice, music=music, use_cache=cached("editor"))
review = rev.run_review(run, final, expected_s)
```

---

## Timing comparison (estimated, 4-shot ad with 3 photos to enhance)

### Before (sequential)
```
triage(5s) + concept(60s) + director(90s) + enhance(30s) + keyframes(60s) + shots(240s) + 
music(15s) + timeline(20s) + voice(15s) + render(45s) + review(5s) = ~585s (~9.75 min)
```

### After (parallelized)
```
triage(5s) + max(concept+director(150s), enhance(30s)) + max(keyframes(20s)+shots(240s), music(15s)) +
timeline(20s) + voice(15s) + render(45s) + review(5s) = ~500s (~8.3 min)
```
With keyframes concurrent: keyframes drops from 60s to ~20s (4 frames at ~15s each, 4 workers).
With Change 4 (pipelined): keyframes hidden behind shots entirely: saves another ~20s → ~480s.

**Net: ~85-105s saved = ~15-18% reduction.** Honest: not "cut by half." The bottleneck is shots
(~240s with concurrency), and that's already parallel. The remaining sequential overhead is
concept+director (~150s of LLM calls + critic loops) which CAN'T be parallelized (each depends
on the previous).

To actually cut to 5 minutes, the paths are:
- Faster Seedance generations (model-side, not ours to control)
- Fewer retries (better prompts → fewer judge failures)
- Fewer/shorter critic loop iterations (concept + director converge faster)
- Reduce the number of seedance_shots per ad (more real_clip/moodboard segments)

---

## Acceptance checks
1. A full run with real keys produces identical output to a pre-change run (same concept, same
   brief, same shots, same final video). The parallelization must not change results.
2. `trace.jsonl` entries are not interleaved/corrupted (thread-safe logging verified).
3. `COST.md` totals match the pre-change run ± rounding (budget tracking thread-safe).
4. When enhance finishes before director, no error. When director finishes before enhance
   (unlikely but possible on very fast LLM + many photos), keyframes correctly waits for
   enhance to complete via `enhance_future.result()`.
5. Timing: measure 3 runs before and 3 after. Expect ~60-100s improvement on a typical
   4-6 seedance_shot run.
6. `--replay` from any step still works (cached stages return immediately; parallelization
   is transparent).

## Guardrails
- No stage logic changes. Only orchestration (run.py) and keyframes' internal loop.
- Thread safety on Run methods is mandatory before shipping — a corrupted trace.jsonl or
  cost.json is worse than a slow pipeline.
- The cost ceiling check must remain serialized (it already is in shots.py via a lock;
  keyframes needs the same pattern).
- Change 4 (pipelined keyframes→shots) is OPTIONAL and should only be built after 1-3
  are measured. Don't pre-commit.
- If fal rate-limits concurrent keyframe calls, reduce MAX_KEYFRAME_CONCURRENCY to 2.
