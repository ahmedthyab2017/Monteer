"""سلسلة الإنتاج: تشغّل سكربتات محرّك video-ad-editor (MIT) بالترتيب، بدون ذكاء اصطناعي في المنتصف.
المرحلة A (تحليل): حذف السكتات ← الكتابة ← قاموس العيادة ← تعليم الهلوسة ← بانتظار المراجعة.
المرحلة B (إنتاج): تعديلات المستخدم ← الكابشن ← حذف الجمل ← القص والزوم ← الرسم ← التصدير ← الصوت ‎-14 LUFS.
"""
import json, os, re, shutil, subprocess, sys

from transcribe import transcribe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.environ.get("MONTEER_ENGINE", os.path.join(ROOT, "engine"))
SCRIPTS = os.path.join(ENGINE, "scripts")
DATA = os.environ.get("MONTEER_DATA", os.path.join(ROOT, "data"))
BRAND_DIR = os.path.join(DATA, "brand")

# جمل يكتبها Whisper من عنده وهي غير موجودة بالصوت (من 02a_whisper_check.py)
HALLU = ["اشترك في القناة", "اشتركوا في القناة", "ترجمة نانسي قنقر", "نانسي قنقر",
         "شكرا للمشاهدة", "شكراً للمشاهدة", "شكرا على المشاهدة", "Amara.org"]
PUNCT = re.compile(r"[\s\u060C\u061B\u061F.,!?:;\"'«»()\[\]…\-]+")


def norm(w):
    return PUNCT.sub("", w or "").strip()


def run(job, args, log_name="log.txt", **kw):
    with open(os.path.join(job.dir, log_name), "a", encoding="utf-8") as lg:
        lg.write("\n$ " + " ".join(args) + "\n")
        lg.flush()
        p = subprocess.run(args, cwd=ENGINE, stdout=lg, stderr=subprocess.STDOUT, **kw)
    if p.returncode != 0:
        raise RuntimeError("فشلت خطوة: " + os.path.basename(args[1] if len(args) > 1 else args[0]))


# ---------------- الهوية ----------------
def load_brand():
    p = os.path.join(BRAND_DIR, "brand.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def save_brand(b):
    os.makedirs(BRAND_DIR, exist_ok=True)
    json.dump(b, open(os.path.join(BRAND_DIR, "brand.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def theme_from_brand(b):
    t = {"bg": b.get("bg", "#14213D"), "ink": "#F5F7FA", "acc": b.get("acc", "#F2C230"),
         "clay": b.get("clay", "#C99A12"), "mut": "#AFC0D6", "font": b.get("font", "Tajawal"),
         "handle": b.get("handle", ""), "grade": False, "faceAnchor": 0.30, "badgeUntil": 0,
         "capStyle": b.get("capStyle", "card"),
         "outro": {"l1": b.get("name", ""), "l2": b.get("address", ""),
                   "chips": b.get("chips", [])[:4], "cta": b.get("cta", "احجز موعدك"),
                   "word": b.get("phone", ""), "sub": b.get("doctor", "")}}
    if os.path.exists(os.path.join(BRAND_DIR, "logo.png")):
        t["logo"] = "logo.png"
    return t


def make_logo_card(src, dst):
    """الشعار على بطاقة بيضاء بزوايا دائرية — يبان على خلفية الختام الغامقة."""
    from PIL import Image, ImageChops, ImageDraw
    im = Image.open(src).convert("RGBA")
    flat = Image.new("RGB", im.size, (255, 255, 255))
    flat.paste(im, mask=im.split()[3])
    diff = ImageChops.difference(flat, Image.new("RGB", im.size, (255, 255, 255))).convert("L").point(lambda p: 255 if p > 25 else 0)
    bb = diff.getbbox()
    if bb:
        im = im.crop(bb)
    S, pad = 900, 70
    card = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, S - 1, S - 1], radius=150, fill=255)
    card.paste(Image.new("RGBA", (S, S), (255, 255, 255, 255)), (0, 0), m)
    w, h = im.size
    k = min((S - 2 * pad) / w, (S - 2 * pad) / h)
    im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    card.alpha_composite(im, ((S - im.size[0]) // 2, (S - im.size[1]) // 2))
    card.save(dst)


def _similar(a, b):
    import difflib
    stop = {"في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "اللي", "و", "او", "أو", "ما", "لا", "يعني"}
    fa, fb = [w for w in a if w not in stop], [w for w in b if w not in stop]
    if not fa or not fb:
        return 0.0
    shared = len(set(fa) & set(fb)) / min(len(fa), len(fb))
    chars = difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    return min(shared, chars) if shared >= 0.6 else 0.0   # الاثنين معاً: كلمات مشتركة وحروف متشابهة


# ---------------- المرحلة A ----------------
def analyze(job):
    W = job.dir
    b = load_brand()
    job.set(stage="cut", msg="أحذف السكتات…", pct=5)
    run(job, [sys.executable, os.path.join(SCRIPTS, "01_cut_plan.py"), W])
    subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(W, "src.mov"), "-vn", "-ac", "1", "-ar", "16000",
                    "-y", os.path.join(W, "a.wav")], check=True)
    job.set(stage="transcribe", msg="أكتب الكلام بتوقيت كل كلمة…", pct=15)
    dic = b.get("dictionary", {})
    prompt = "، ".join(list(dict.fromkeys(list(dic.values()) + b.get("hot", []))))
    d = transcribe(os.path.join(W, "a.wav"), W, prompt)
    json.dump(d, open(os.path.join(W, "a_raw.json"), "w", encoding="utf-8"), ensure_ascii=False)
    # قاموس العيادة: يصلح الأخطاء المتكررة كلمة بكلمة
    fixed = 0
    sents = []
    for s in d["segments"]:
        if not s.get("words"):
            continue
        for w in s["words"]:
            k = norm(w["word"])
            if k in dic:
                w["word"] = " " + dic[k]
                fixed += 1
        text = " ".join(norm(w["word"]) or w["word"].strip() for w in s["words"])
        sents.append({"start": round(s["words"][0]["start"], 2), "end": round(s["words"][-1]["end"], 2),
                      "orig": text, "text": text,
                      "drop": any(h in s["text"] for h in HALLU),
                      "flag": "جملة يكتبها Whisper من عنده — غير موجودة بالصوت" if any(h in s["text"] for h in HALLU) else ""})
    d["segments"] = [s for s in d["segments"] if s.get("words")]
    # الجملة المعادة: لما يعيد صياغة جملة، الأولى غالباً هي الغلط
    for i in range(len(sents) - 1):
        if sents[i]["drop"]:
            continue
        a_, b_ = sents[i]["text"].split(), sents[i + 1]["text"].split()
        if len(a_) >= 3 and _similar(a_, b_) >= 0.6:
            sents[i]["drop"] = True
            sents[i]["flag"] = "يبدو أنك أعدت هذه الجملة في التي بعدها — اقترحت حذفها"
    json.dump(d, open(os.path.join(W, "a.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(sents, open(os.path.join(W, "sentences.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    job.set(stage="review", msg="راجع الكلام قبل الإنتاج", pct=30, engine=d.get("engine"), dict_fixed=fixed)


# كلمات شائعة لا نحفظ تصحيحها: تصحيحها يعتمد على سياق الجملة لا على خطأ في السمع
STOP = {"في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه", "هذي", "ذلك", "اللي", "التي", "الذي", "و", "او",
        "أو", "ما", "لا", "ولا", "يعني", "كان", "كانت", "يكون", "أن", "ان", "إن", "هو", "هي", "نحن", "أنا", "انا",
        "حتى", "إذا", "اذا", "بس", "شوية", "ممكن", "أسنان", "الأسنان", "اسنان", "عالي", "عالية"}


def _learn(b, pairs, need=2):
    """يحفظ التصحيح في قاموس العيادة فقط لما يتكرر نفس التصحيح مرتين (بنفس الفيديو أو بفيديوهات مختلفة).
    تصحيح سياقي (إضافة «بـ» أو «ال»، تنوين، كلمة شائعة) لا يُحفظ أبداً."""
    def bare(w):
        return re.sub(r"[\u064B-\u0652\u0640]", "", w)
    cand = b.get("candidates", {})
    dic = b.get("dictionary", {})
    promoted = 0
    for o, n in pairs:
        if len(o) < 4 or o in STOP or o in dic or bare(o) == bare(n):
            continue
        if n.endswith(o) or o.endswith(n) or n.startswith(o) or o.startswith(n):
            continue
        k = o + "→" + n
        cand[k] = cand.get(k, 0) + 1
        if cand[k] >= need:
            dic[o] = n
            cand.pop(k)
            promoted += 1
    b["candidates"], b["dictionary"] = cand, dic
    save_brand(b)
    return promoted


# ---------------- المرحلة B ----------------
def _rebuild_words(seg, text):
    """نص معدّل بعدد كلمات مختلف: نوزّع الكلمات الجديدة على زمن الجملة بالتناسب مع طول كل كلمة."""
    words = text.split()
    a, z = seg["words"][0]["start"], seg["words"][-1]["end"]
    total = sum(len(w) + 1 for w in words) or 1
    out, t = [], a
    for w in words:
        dt = (z - a) * (len(w) + 1) / total
        out.append({"word": " " + w, "start": round(t, 3), "end": round(t + dt, 3)})
        t += dt
    return out


def produce(job, edits):
    W = job.dir
    b = load_brand()
    d = json.load(open(os.path.join(W, "a.json"), encoding="utf-8"))
    segs = d["segments"]
    learned_pairs = []
    drop_idx = []
    for i, (s, e) in enumerate(zip(segs, edits)):
        new = " ".join(e["text"].split())
        old = [norm(w["word"]) or w["word"].strip() for w in s["words"]]
        if e.get("drop") or not new:
            drop_idx.append(i + 1)
            continue
        nw = new.split()
        if len(nw) == len(old):
            for o, n in zip(old, nw):
                if o != n and o and n:
                    learned_pairs.append((o, n))
            for w, n in zip(s["words"], nw):
                w["word"] = " " + n
        else:
            s["words"] = _rebuild_words(s, new)
        s["text"] = " " + new
    json.dump(d, open(os.path.join(W, "a.json"), "w", encoding="utf-8"), ensure_ascii=False)
    promoted = _learn(b, learned_pairs)
    # الجمل المحذوفة: تنشال من الكلام ومن الصوت والصورة (نطرح زمنها من مقاطع القص)
    if drop_idx:
        cut = json.load(open(os.path.join(W, "cut.json"), encoding="utf-8"))
        keep = cut["keep"]
        for i in drop_idx:
            s = segs[i - 1]
            a, z = s["words"][0]["start"] - 0.05, s["words"][-1]["end"] + 0.05
            nk = []
            for k0, k1 in keep:
                if k1 <= a or k0 >= z:
                    nk.append([k0, k1])
                    continue
                if k0 < a - 0.2:
                    nk.append([k0, a])
                if k1 > z + 0.2:
                    nk.append([z, k1])
            keep = nk
        cut["keep"] = keep
        cut.pop("zooms", None)
        json.dump(cut, open(os.path.join(W, "cut.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        d["segments"] = [s for j, s in enumerate(segs) if (j + 1) not in drop_idx]
        json.dump(d, open(os.path.join(W, "a.json"), "w", encoding="utf-8"), ensure_ascii=False)
        segs = d["segments"]
    fix = [[norm(w["word"]) or w["word"].strip() for w in s["words"]] for s in segs]
    json.dump({"fix": fix, "hot": b.get("hot", [])}, open(os.path.join(W, "fixes.json"), "w", encoding="utf-8"), ensure_ascii=False)

    job.set(stage="captions", msg="أركّب الكابشن على توقيت الصوت…", pct=35)
    run(job, [sys.executable, os.path.join(SCRIPTS, "02_captions.py"), W])
    job.set(stage="zoom", msg="أقص وأضيف الزوم…", pct=42)
    run(job, [sys.executable, os.path.join(SCRIPTS, "03_cut_zoom.py"), W])

    # القالب والهوية
    comp = open(os.path.join(SCRIPTS, "compose.REFERENCE.html"), encoding="utf-8").read()
    cap = int(b.get("capBottom", 1290))
    comp = comp.replace("(LOW?_R.y-60+SEAM:1460))-bh", f"(LOW?_R.y-60+SEAM:{cap}))-bh")
    comp = comp.replace("const L=180,fl=", "const L=250,fl=").replace("X.drawImage(LOGO,540-L/2,196+fl", "X.drawImage(LOGO,540-L/2,180+fl")
    open(os.path.join(W, "compose.html"), "w", encoding="utf-8").write(comp)
    json.dump(theme_from_brand(b), open(os.path.join(W, "theme.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if os.path.exists(os.path.join(BRAND_DIR, "logo.png")):
        shutil.copy(os.path.join(BRAND_DIR, "logo.png"), os.path.join(W, "logo.png"))
    total = json.load(open(os.path.join(W, "caps.json"), encoding="utf-8"))["total"]
    json.dump({"outro": 5.2, "whoosh_up": [total]}, open(os.path.join(W, "sfx.json"), "w"))
    run(job, [sys.executable, os.path.join(SCRIPTS, "05_sfx.py"), W])

    job.set(stage="render", msg="أرسم الكابشن والخاتمة…", pct=45)
    p = subprocess.Popen(["node", os.path.join(SCRIPTS, "04_render_frames.js"), W, "all", "--force"], cwd=ENGINE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    with open(os.path.join(W, "log.txt"), "a", encoding="utf-8") as lg:
        for line in p.stdout:
            lg.write(line)
            m = re.search(r"(\d+)\s*/\s*(\d+)", line)
            if m and line.startswith("فريم"):
                job.set(pct=45 + int(45 * int(m.group(1)) / max(1, int(m.group(2)))))
    if p.wait() != 0:
        raise RuntimeError("فشل الرسم")
    job.set(stage="encode", msg="أصدّر الفيديو وأضبط الصوت…", pct=92)
    run(job, ["bash", os.path.join(SCRIPTS, "06_encode.sh"), W])
    run(job, ["bash", os.path.join(SCRIPTS, "06c_loudfix.sh"), os.path.join(W, "ad-final.mp4"), os.path.join(W, "final.mp4")])
    job.set(stage="done", msg="الريل جاهز", pct=100, learned=promoted)
