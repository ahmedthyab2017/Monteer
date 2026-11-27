"""مونتير — خادم الواجهة والمهام.  تشغيل:  uvicorn app:app --host 0.0.0.0 --port 8080  (من مجلد server)"""
import json, os, queue, shutil, threading, time, traceback, uuid

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import pipeline

ROOT = pipeline.ROOT
JOBS = os.path.join(pipeline.DATA, "jobs")
os.makedirs(JOBS, exist_ok=True)
# أول تشغيل على قرص دائم فارغ: ننسخ هوية سوران الجاهزة من seed/brand
_seed = os.path.join(ROOT, "seed", "brand")
if os.path.isdir(_seed) and not os.path.exists(os.path.join(pipeline.BRAND_DIR, "brand.json")):
    shutil.copytree(_seed, pipeline.BRAND_DIR, dirs_exist_ok=True)
PASSWORD = os.environ.get("MONTEER_PASSWORD", "")
KEEP_DAYS = int(os.environ.get("MONTEER_KEEP_DAYS", "30"))   # خصوصية المرضى: تُحذف الفيديوهات بعدها

app = FastAPI(title="Monteer")
CAP_STYLES = {"card", "shadow", "big", "underline", "bar", "chunk"}
Q = queue.Queue()


class Job:
    def __init__(self, jid):
        self.id, self.dir = jid, os.path.join(JOBS, jid)

    @property
    def meta_path(self):
        return os.path.join(self.dir, "job.json")

    def get(self):
        try:
            return json.load(open(self.meta_path, encoding="utf-8"))
        except FileNotFoundError:
            raise HTTPException(404, "غير موجود")

    def set(self, **kw):
        m = self.get() if os.path.exists(self.meta_path) else {}
        m.update(kw, updated=time.time())
        tmp = self.meta_path + ".tmp"
        json.dump(m, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, self.meta_path)


def worker():
    while True:
        kind, jid, payload = Q.get()
        job = Job(jid)
        try:
            if kind == "analyze":
                pipeline.analyze(job)
            else:
                pipeline.produce(job, payload["edits"], payload.get("opts"))
        except Exception as e:
            traceback.print_exc()
            job.set(stage="error", msg=str(e) or "حدث خطأ")
        Q.task_done()


def cleanup():
    while True:
        cut = time.time() - KEEP_DAYS * 86400
        for j in os.listdir(JOBS):
            p = os.path.join(JOBS, j)
            if os.path.isdir(p) and os.path.getmtime(p) < cut:
                shutil.rmtree(p, ignore_errors=True)
        time.sleep(6 * 3600)


threading.Thread(target=worker, daemon=True).start()
threading.Thread(target=cleanup, daemon=True).start()


def auth(key):
    if PASSWORD and key != PASSWORD:
        raise HTTPException(401, "كلمة المرور غير صحيحة")


@app.get("/api/ping")
def ping(x_key: str = Header("")):
    auth(x_key)
    return {"ok": True, "engine": "groq" if os.environ.get("GROQ_API_KEY") else "local", "queue": Q.qsize()}


@app.post("/api/jobs")
async def create_job(video: UploadFile = File(...), x_key: str = Header("")):
    auth(x_key)
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job = Job(jid)
    os.makedirs(job.dir)
    with open(os.path.join(job.dir, "src.mov"), "wb") as f:
        while chunk := await video.read(1 << 20):
            f.write(chunk)
    job.set(id=jid, name=video.filename, stage="queued", msg="في الطابور…", pct=1, created=time.time())
    Q.put(("analyze", jid, None))
    return job.get()


# ---- الرفع على قطع: بوابة الاستضافة ترفض الطلب الأكبر من ~25 ميغا، والنت الضعيف يقطع الرفع الطويل ----
UPLOADS = os.path.join(pipeline.DATA, "uploads")
os.makedirs(UPLOADS, exist_ok=True)


@app.post("/api/uploads")
def start_upload(x_key: str = Header("")):
    auth(x_key)
    uid = uuid.uuid4().hex
    os.makedirs(os.path.join(UPLOADS, uid))
    return {"uid": uid}


@app.put("/api/uploads/{uid}/{n}")
async def put_chunk(uid: str, n: int, request: Request, x_key: str = Header("")):
    auth(x_key)
    d = os.path.join(UPLOADS, os.path.basename(uid))
    if not os.path.isdir(d) or n < 0 or n > 10000:
        raise HTTPException(404, "رفع غير معروف")
    tmp = os.path.join(d, f"{n:05d}.part.tmp")
    with open(tmp, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
    os.replace(tmp, os.path.join(d, f"{n:05d}.part"))   # القطعة تُعتمد فقط إذا وصلت كاملة
    return {"ok": True, "n": n}


@app.post("/api/uploads/{uid}/done")
def finish_upload(uid: str, body: dict, x_key: str = Header("")):
    auth(x_key)
    d = os.path.join(UPLOADS, os.path.basename(uid))
    parts = sorted(f for f in os.listdir(d) if f.endswith(".part")) if os.path.isdir(d) else []
    total = int(body.get("parts", 0))
    if not parts or len(parts) != total:
        raise HTTPException(400, f"وصل {len(parts)} من {total} قطعة")
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job = Job(jid)
    os.makedirs(job.dir)
    with open(os.path.join(job.dir, "src.mov"), "wb") as out:
        for f in parts:
            with open(os.path.join(d, f), "rb") as inp:
                shutil.copyfileobj(inp, out, 1 << 20)
    shutil.rmtree(d, ignore_errors=True)
    job.set(id=jid, name=str(body.get("name", ""))[:120], stage="queued", msg="في الطابور…", pct=1, created=time.time())
    Q.put(("analyze", jid, None))
    return job.get()


@app.get("/api/jobs")
def list_jobs(x_key: str = Header("")):
    auth(x_key)
    out = []
    for j in sorted(os.listdir(JOBS), reverse=True)[:30]:
        try:
            out.append(Job(j).get())
        except HTTPException:
            pass
    return out


@app.get("/api/jobs/{jid}")
def get_job(jid: str, x_key: str = Header("")):
    auth(x_key)
    job = Job(os.path.basename(jid))
    m = job.get()
    sp = os.path.join(job.dir, "sentences.json")
    if os.path.exists(sp):
        m["sentences"] = json.load(open(sp, encoding="utf-8"))
    return m


@app.post("/api/jobs/{jid}/produce")
def produce(jid: str, body: dict, x_key: str = Header("")):
    auth(x_key)
    job = Job(os.path.basename(jid))
    m = job.get()
    if m.get("stage") not in ("review", "done", "error"):
        raise HTTPException(409, "المهمة ما زالت تعمل")
    sents = json.load(open(os.path.join(job.dir, "sentences.json"), encoding="utf-8"))
    edits = body.get("sentences", [])
    if len(edits) != len(sents):
        raise HTTPException(400, "عدد الجمل لا يطابق")
    for s, e in zip(sents, edits):
        s["text"], s["drop"] = e.get("text", s["text"]), bool(e.get("drop"))
    json.dump(sents, open(os.path.join(job.dir, "sentences.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if m.get("stage") != "review":     # إعادة إنتاج: نرجع لنسخة التحليل الأصلية
        shutil.copy(os.path.join(job.dir, "a_review.json"), os.path.join(job.dir, "a.json"))
        for f in ("cut.json.orig",):
            if os.path.exists(os.path.join(job.dir, f)):
                shutil.copy(os.path.join(job.dir, f), os.path.join(job.dir, "cut.json"))
    else:
        shutil.copy(os.path.join(job.dir, "a.json"), os.path.join(job.dir, "a_review.json"))
        shutil.copy(os.path.join(job.dir, "cut.json"), os.path.join(job.dir, "cut.json.orig"))
    st = body.get("capStyle")
    opts = {"capStyle": st} if st in CAP_STYLES else {}
    job.set(stage="queued", msg="في الطابور…", pct=32, capStyle=opts.get("capStyle"))
    Q.put(("produce", job.id, {"edits": edits, "opts": opts}))
    return job.get()


@app.get("/api/jobs/{jid}/video")
def video(jid: str, k: str = ""):
    auth(k)
    p = os.path.join(JOBS, os.path.basename(jid), "final.mp4")
    if not os.path.exists(p):
        raise HTTPException(404, "الفيديو غير جاهز")
    return FileResponse(p, media_type="video/mp4", filename=f"reel-{os.path.basename(jid)}.mp4")


def _job_file(jid, name, k, media):
    auth(k)
    p = os.path.join(JOBS, os.path.basename(jid), name)
    if not os.path.exists(p):
        raise HTTPException(404, "غير موجود")
    return FileResponse(p, media_type=media)


@app.get("/api/jobs/{jid}/preview")
def preview(jid: str, k: str = ""):
    return _job_file(jid, "preview.mp4", k, "video/mp4")


@app.get("/api/jobs/{jid}/thumb.jpg")
def thumb(jid: str, k: str = ""):
    return _job_file(jid, "thumb.jpg", k, "image/jpeg")


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str, x_key: str = Header("")):
    auth(x_key)
    d = os.path.join(JOBS, os.path.basename(jid))
    m = Job(os.path.basename(jid)).get()
    if m.get("stage") not in ("review", "done", "error"):
        raise HTTPException(409, "لا يمكن الحذف أثناء العمل")
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}


@app.get("/api/brand")
def get_brand(x_key: str = Header("")):
    auth(x_key)
    b = pipeline.load_brand()
    b["hasLogo"] = os.path.exists(os.path.join(pipeline.BRAND_DIR, "logo.png"))
    return b


@app.post("/api/brand")
def set_brand(body: dict, x_key: str = Header("")):
    auth(x_key)
    b = pipeline.load_brand()
    body.pop("hasLogo", None)
    b.update(body)
    pipeline.save_brand(b)
    return b


@app.post("/api/brand/logo")
async def set_logo(logo: UploadFile = File(...), x_key: str = Header("")):
    auth(x_key)
    os.makedirs(pipeline.BRAND_DIR, exist_ok=True)
    raw = os.path.join(pipeline.BRAND_DIR, "logo_src")
    open(raw, "wb").write(await logo.read())
    pipeline.make_logo_card(raw, os.path.join(pipeline.BRAND_DIR, "logo.png"))
    return {"ok": True}


@app.get("/api/brand/logo.png")
def logo_png():
    p = os.path.join(pipeline.BRAND_DIR, "logo.png")
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p)


app.mount("/", StaticFiles(directory=os.path.join(ROOT, "web"), html=True), name="web")
