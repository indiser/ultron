import os, requests

URL = "https://terminal-counsel-weeks-breath.trycloudflare.com"
KEY = "k4PjKcDf5RC6_oq_NSKOrMZF55o"
REF = "ultron_best_vo.mp3"
H = {"Authorization": f"Bearer {KEY}"}

print("health:", requests.get(f"{URL}/health", timeout=30).text)

# 1. upload voice (once per Colab session)
r = requests.post(f"{URL}/v1/audio/voices", headers=H, timeout=120,
    files={"audio_sample": open(REF, "rb")},
    data={"name": "me", "consent": "my-own-voice", "speaker_description": "ultron"})
print("upload:", r.status_code, r.text[:300])

# 2. speak
r = requests.post(f"{URL}/v1/audio/speech", headers=H, timeout=300, json={
    "input": "Hello boss, systems online.",
    "voice": "me",
    "response_format": "wav",
    "extra_params": {"lang": "en"}})
print("speech:", r.status_code, r.headers.get("content-type"), len(r.content), "bytes")

if r.status_code == 200 and len(r.content) > 1000:
    open("out.wav", "wb").write(r.content)
    print("saved out.wav")
    os.startfile("out.wav")      # Windows: plays it
else:
    print(r.text[:500])

import requests

# URL = "https://pop-seminars-airplane-styles.trycloudflare.com"
# KEY     = "6jUZPuo9IOO2aJWTYY2SWVYOftM"
# H = {"Authorization": f"Bearer {KEY}"}
# TEXT = "Hello boss, systems online."

# PRESETS = {
#     "neutral": None,
#     "happy":   [0.8, 0, 0, 0, 0, 0, 0, 0],
#     "angry":   [0, 0.8, 0, 0, 0, 0, 0, 0],
#     "sad":     [0, 0, 0.8, 0, 0, 0, 0, 0],
#     "cold":    [0, 0.3, 0, 0, 0, 0, 0, 0.7],   # angry + calm, Ultron-ish
# }

# for name, vec in PRESETS.items():
#     ep = {"lang": "en"}
#     if vec:
#         ep["emo_vector"] = vec
#         ep["emo_alpha"] = 0.8
#     r = requests.post(f"{URL}/v1/audio/speech", headers=H, timeout=300, json={
#         "input": TEXT, "voice": "me", "response_format": "wav", "extra_params": ep})
#     print(name, r.status_code, len(r.content))
#     if r.status_code == 200:
#         open(f"emo_{name}.wav", "wb").write(r.content)
#     else:
#         print(r.text[:300])