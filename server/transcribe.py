"""الكتابة (التفريغ) بتوقيت الكلمة.
- لو GROQ_API_KEY موجود: Whisper large-v3 عبر Groq (الأدق والأسرع، ولا يحتاج ذاكرة على الخادم).
- وإلا: Whisper محلي (الافتراضي turbo — large-v3 يحتاج أكثر من 8 جيجا ذاكرة).
المخرج دائماً بنفس شكل openai-whisper: {"segments":[{"start","end","text","words":[{"word","start","end"}]}]}
"""
import json, os, subprocess, sys

import requests

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _groq(wav, prompt):
    key = os.environ["GROQ_API_KEY"]
    with open(wav, "rb") as f:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {key}"},
            files={"file": ("a.wav", f, "audio/wav")},
            data=[("model", os.environ.get("GROQ_MODEL", "whisper-large-v3")),
                  ("language", "ar"), ("response_format", "verbose_json"),
                  ("temperature", "0"),
                  ("timestamp_granularities[]", "word"),
                  ("timestamp_granularities[]", "segment")],
            timeout=600)
    r.raise_for_status()
    d = r.json()
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"], "words": []} for s in d.get("segments", [])]
    for w in d.get("words", []):
        mid = (w["start"] + w["end"]) / 2
        tgt = next((s for s in segs if s["start"] <= mid <= s["end"]), None)
        if tgt is None and segs:
            tgt = min(segs, key=lambda s: min(abs(s["start"] - mid), abs(s["end"] - mid)))
        if tgt is not None:
            tgt["words"].append({"word": " " + w["word"].strip(), "start": w["start"], "end": w["end"]})
    return {"segments": [s for s in segs if s["words"]], "engine": "groq"}


def _local(wav, outdir, prompt):
    model = os.environ.get("MONTEER_LOCAL_MODEL", "turbo")
    cmd = [sys.executable, "-m", "whisper", wav, "--language", "ar", "--model", model,
           "--word_timestamps", "True", "--output_format", "json", "--output_dir", outdir,
           "--fp16", "False", "--verbose", "False"]
    # لا نمرّر قائمة مصطلحات (initial_prompt): جرّبناها على فيديو حقيقي فدفعت الكتابة نحو الفصحى
    # وأضافت جملاً لم تُقل. القاموس بعد الكتابة أضمن.
    subprocess.run(cmd, check=True, capture_output=True)
    d = json.load(open(os.path.join(outdir, os.path.splitext(os.path.basename(wav))[0] + ".json"), encoding="utf-8"))
    d["engine"] = "local-" + model
    return d


def transcribe(wav, outdir, prompt=""):
    fx = os.environ.get("MONTEER_TRANSCRIPT_FIXTURE")   # للاختبار فقط: كتابة جاهزة بدل الاتصال بـ Groq
    if fx and os.path.exists(fx):
        d = json.load(open(fx, encoding="utf-8"))
        d["engine"] = "fixture"
        return d
    if os.environ.get("GROQ_API_KEY"):
        return _groq(wav, prompt)
    return _local(wav, outdir, prompt)
