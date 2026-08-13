# -*- coding: utf-8 -*-
"""
墨墨背单词桌面版 —— 右下角常驻的墨墨风格学习悬浮窗
- 单词 + 音标 + 词义 + 例句 + 发音,始终置顶
- 墨墨开放 API 联动:拉取今日学习单词、添加单词双向同步
  (token 获取:墨墨背单词 App -> 我的 -> 更多设置 -> 实验功能 -> 开放 API)
- 无 token 时自动使用本地 words.txt,音标/词义/例句由有道词典补全(带缓存)
"""
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

import requests

FROZEN = getattr(sys, "frozen", False)
BASE_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
WORDS_PATH = os.path.join(BASE_DIR, "words.txt")
MASTERED_PATH = os.path.join(BASE_DIR, "mastered.txt")
CACHE_PATH = os.path.join(BASE_DIR, "cache.json")
LOCK_PATH = os.path.join(BASE_DIR, ".lock")
INDEX_PATH = os.path.join(RES_DIR, "web", "index.html")

API_BASE = "https://open.maimemo.com/open/api/v1/memo"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

DEFAULTS = {
    "token": "",
    "use_api": True,
    "show_word_sec": 6,
    "show_meaning_sec": 5,
    "corner": "bottom_right",
    "tts": "edge",
    "youdao_enrich": True,
    "auto_mode": True,
}

_session = requests.Session()
_cache_lock = threading.Lock()


# ---------------- 配置 / 缓存 ----------------
def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache):
    try:
        with _cache_lock:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------- 墨墨开放 API ----------------
def _headers():
    cfg = load_config()
    h = {"Accept": "application/json", "User-Agent": UA}
    tok = (cfg.get("token") or "").strip()
    if tok:
        h["Authorization"] = "Bearer " + tok
    return h


def api_get(path, params):
    r = _session.get(API_BASE + path, params=params, headers=_headers(), timeout=12)
    r.raise_for_status()
    return r.json()


def api_post(path, body):
    h = _headers()
    h["Content-Type"] = "application/json"
    r = _session.post(API_BASE + path, json=body, headers=h, timeout=12)
    r.raise_for_status()
    return r.json()


def fetch_today_items():
    """拉取今日学习单词(公测接口,需App当日打开过且开启自动同步)"""
    j = api_post("/study/get_today_items", {"is_finished": False, "limit": 1000})
    out = []
    for it in (j.get("today_items") or []):
        sp = (it.get("voc_spelling") or "").strip()
        if sp:
            out.append({
                "spelling": sp,
                "voc_id": it.get("voc_id") or "",
                "is_new": bool(it.get("is_new")),
                "is_finished": bool(it.get("is_finished")),
                "order": it.get("order") or 0,
            })
    return out


def api_voc_id(spelling):
    j = api_get("/vocabulary", {"spelling": spelling})
    voc = j.get("voc") or {}
    return voc.get("id") or ""


def api_add_words(ids, advance=False):
    j = api_post("/study/add_words", {"words": [{"id": i} for i in ids], "advance": advance})
    return j.get("added_count", 0)


# ---------------- 本地词表 ----------------
def split_pair(line):
    for sep in ("\t", " | ", "|", " - ", "—", "：", ":", "，", ","):
        if sep in line:
            i = line.find(sep)
            w, m = line[:i].strip(), line[i + len(sep):].strip()
            if w:
                return w, m
    parts = line.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return line, ""


def load_local_words():
    words = {}
    if os.path.exists(WORDS_PATH):
        with open(WORDS_PATH, encoding="utf-8") as f:
            for ln in f:
                s = ln.strip()
                if not s or s.startswith("#") or s.startswith("//"):
                    continue
                spelling, meaning = split_pair(s)
                if spelling and spelling.lower() not in words:
                    words[spelling.lower()] = {"spelling": spelling, "meaning": meaning}
    return words


def load_mastered():
    s = set()
    if os.path.exists(MASTERED_PATH):
        with open(MASTERED_PATH, encoding="utf-8") as f:
            for ln in f:
                t = ln.strip()
                if t:
                    s.add(t.split("|")[0].strip().lower())
    return s


def append_mastered(spelling):
    with open(MASTERED_PATH, "a", encoding="utf-8") as f:
        f.write("{} | {}\n".format(spelling, time.strftime("%Y-%m-%d %H:%M")))


# ---------------- 复习状态(认识/模糊/忘记 的间隔记忆) ----------------
REVIEW_PATH = os.path.join(BASE_DIR, "review.json")


def load_review():
    try:
        with open(REVIEW_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_review(rev):
    try:
        with _cache_lock:
            with open(REVIEW_PATH, "w", encoding="utf-8") as f:
                json.dump(rev, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------- 词典补全(有道,带缓存) ----------------
def enrich(spelling, voc_id=""):
    cache = load_cache()
    key = spelling.lower()
    hit = cache.get(key)
    if hit and hit.get("meanings"):
        return hit
    info = {"phonetic": "", "meanings": [], "examples": [], "source": "local"}
    cfg = load_config()
    tok = (cfg.get("token") or "").strip()

    if tok and voc_id:
        try:
            j = api_get("/interpretations", {"voc_id": voc_id})
            for it in (j.get("interpretations") or [])[:3]:
                content = it.get("content")
                if isinstance(content, str) and content.strip():
                    for part in re.split(r"[\n;；]", content):
                        part = part.strip()
                        if part and part not in info["meanings"]:
                            info["meanings"].append(part)
            if info["meanings"]:
                info["source"] = "maimemo"
        except Exception:
            pass
        try:
            j = api_get("/phrases", {"voc_id": voc_id})
            for ph in (j.get("phrases") or [])[:3]:
                en = (ph.get("phrase") or "").strip()
                if en:
                    info["examples"].append({"en": en, "zh": (ph.get("interpretation") or "").strip()})
        except Exception:
            pass

    if cfg.get("youdao_enrich", True):
        try:
            youdao_fill(spelling, info)
        except Exception:
            pass

    if info["meanings"] or info["examples"]:
        cache[key] = info
        save_cache(cache)
    return info


def youdao_fill(word, info):
    r = _session.get("https://dict.youdao.com/jsonapi", params={"q": word},
                     headers={"User-Agent": UA}, timeout=10)
    j = r.json()
    ec = (j.get("ec") or {}).get("word") or [{}]
    entry = ec[0] if ec else {}
    us = entry.get("usphone") or entry.get("ukphone")
    if us and not info["phonetic"]:
        info["phonetic"] = "/{}/".format(us)
    for tr in entry.get("trs") or []:
        for t in tr.get("tr") or []:
            l = t.get("l") or {}
            i = l.get("i")
            txt = "".join(i) if isinstance(i, list) else (str(i) if i else "")
            txt = txt.strip()
            if txt and txt not in info["meanings"]:
                info["meanings"].append(txt)
    for e in (entry.get("example") or []):
        en = (e.get("sentence") or "").strip()
        if en and len(info["examples"]) < 3:
            info["examples"].append({"en": en, "zh": (e.get("translation") or "").strip()})
    if info["meanings"] and info["source"] == "local":
        info["source"] = "youdao"


# ---------------- 发音 ----------------
def speak(spelling):
    threading.Thread(target=_speak, args=(spelling,), daemon=True).start()


def _speak(word):
    cfg = load_config()
    if cfg.get("tts", "edge") == "edge":
        try:
            _edge_tts(word)
            return
        except Exception:
            pass
    try:
        _sapi(word)
    except Exception:
        pass


def _edge_tts(word):
    import asyncio
    import edge_tts
    out = os.path.join(tempfile.gettempdir(), "mm_speak.mp3")

    async def go():
        com = edge_tts.Communicate(word, "en-US-AriaNeural")
        await com.save(out)

    asyncio.run(go())
    _play_mp3(out)


def _play_mp3(path):
    mci = ctypes.windll.winmm.mciSendStringW
    mci('open "{}" type mpegvideo alias w'.format(path), None, 0, 0)
    mci("play w", None, 0, 0)
    threading.Timer(8.0, lambda: mci("close w", None, 0, 0)).start()


def _sapi(word):
    ps = ('Add-Type -AssemblyName System.Speech;'
          '$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;'
          '$s.Speak("{}")'.format(word.replace('"', "'")))
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ---------------- 窗口定位 ----------------
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def work_area():
    r = _RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right, r.bottom


def position_for(win, corner, w, h):
    left, top, right, bottom = work_area()
    pad = 12
    if corner == "bottom_left":
        x, y = left + pad, bottom - h - pad
    elif corner == "top_right":
        x, y = right - w - pad, top + pad
    elif corner == "top_left":
        x, y = left + pad, top + pad
    else:
        x, y = right - w - pad, bottom - h - pad
    try:
        win.move(x, y)
    except Exception:
        pass


# ---------------- 单实例(命名互斥体,进程退出自动释放) ----------------
_mutex_handle = None


def acquire_lock():
    global _mutex_handle
    try:
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MaimemoWordsDesktop")
        return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


# ---------------- JS 桥 ----------------
class Api:
    def __init__(self, window):
        self.win = window
        self.pool = []
        self.later = []          # 模糊词:{w: 词dict, due: 时间戳}
        self.pool_ready = False
        self.pool_error = ""
        self.mastered = load_mastered()
        threading.Thread(target=self._init_pool, daemon=True).start()

    def _init_pool(self):
        try:
            cfg = load_config()
            tok = (cfg.get("token") or "").strip()
            local = load_local_words()
            merged = {}
            rev = load_review()
            now = time.time()
            skip = lambda k: k in self.mastered or (k in rev and rev[k].get("due", 0) > now)
            if tok and cfg.get("use_api", True):
                try:
                    for it in fetch_today_items():
                        k = it["spelling"].lower()
                        if skip(k):
                            continue
                        merged[k] = {
                            "spelling": it["spelling"], "voc_id": it["voc_id"],
                            "is_new": it["is_new"], "source": "maimemo",
                            "local_meaning": ""}
                except Exception as e:
                    self.pool_error = "墨墨同步失败:{}".format(e)
            for sp, v in local.items():
                if skip(sp):
                    continue
                if sp in merged:
                    merged[sp]["local_meaning"] = v["meaning"]
                else:
                    merged[sp] = {"spelling": v["spelling"], "voc_id": "",
                                  "is_new": False, "source": "local",
                                  "local_meaning": v["meaning"]}
            self.pool = list(merged.values())
            if cfg.get("shuffle", True):
                random.shuffle(self.pool)
        except Exception as e:
            self.pool_error = str(e)
        finally:
            self.pool_ready = True

    def get_state(self):
        cfg = load_config()
        tok = (cfg.get("token") or "").strip()
        return {
            "ready": self.pool_ready,
            "mode": "maimemo" if tok and cfg.get("use_api", True) else "local",
            "total": len(self.pool),
            "error": self.pool_error,
            "cfg": cfg,
        }

    def get_words(self, start=0, count=600):
        # 到期的模糊词自动回到词池
        now = time.time()
        due = [x for x in self.later if x.get("due", 0) <= now]
        if due:
            self.pool.extend(x["w"] for x in due)
            self.later = [x for x in self.later if x.get("due", 0) > now]
        return self.pool[start:start + count]

    def get_detail(self, spelling):
        for w in self.pool:
            if w["spelling"].lower() == spelling.lower():
                info = enrich(w["spelling"], w.get("voc_id", ""))
                return dict(w, **info)
        info = enrich(spelling, "")
        return dict({"spelling": spelling, "voc_id": "", "is_new": False,
                     "source": "local", "local_meaning": ""}, **info)

    def speak(self, spelling):
        speak(spelling)
        return {"ok": True}

    def mark_mastered(self, spelling):
        append_mastered(spelling)
        self.mastered.add(spelling.lower())
        self.pool = [w for w in self.pool if w["spelling"].lower() != spelling.lower()]
        return {"ok": True, "total": len(self.pool)}

    def mark_vague(self, spelling):
        """模糊:10分钟后自动回来复习(本地间隔记忆)"""
        key = spelling.lower()
        rev = load_review()
        rev[key] = {"level": "vague", "due": time.time() + 600}
        save_review(rev)
        w = None
        for i, x in enumerate(self.pool):
            if x["spelling"].lower() == key:
                w = self.pool.pop(i)
                break
        if w:
            self.later.append({"w": w, "due": time.time() + 600})
        return {"ok": True, "total": len(self.pool) + len(self.later),
                "msg": "已标记模糊,10分钟后自动回来复习"}

    def mark_forget(self, spelling):
        """忘记:移到队尾,马上再看一遍"""
        key = spelling.lower()
        for i, x in enumerate(self.pool):
            if x["spelling"].lower() == key:
                w = self.pool.pop(i)
                self.pool.append(w)
                break
        return {"ok": True, "total": len(self.pool), "msg": "已标记忘记,稍后再看一遍"}

    def add_preview(self, spelling):
        spelling = (spelling or "").strip()
        if not spelling:
            return {"ok": False, "msg": "请输入单词"}
        info = enrich(spelling, "")
        return {"ok": True, "spelling": spelling,
                "phonetic": info.get("phonetic", ""),
                "meanings": info.get("meanings", []),
                "examples": info.get("examples", []),
                "source": info.get("source", "local")}

    def import_notepads(self):
        """从墨墨云词本导入单词(需在App里创建云词本)"""
        try:
            j = api_get("/notepads", {})
            pads = ((j.get("data") or j).get("notepads")) or []
            if not pads:
                return {"ok": False, "msg": "云词本为空:在墨墨App里创建云词本、添加单词后,再来导入"}
            added = 0
            for p in pads:
                pid = p.get("id")
                if not pid:
                    continue
                d = api_get("/notepads/" + pid, {})
                np = ((d.get("data") or d).get("notepad")) or d
                content = np.get("content") or ""
                for w in re.split(r"[\s,，、;\n]+", str(content)):
                    w = w.strip()
                    if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", w):
                        continue
                    k = w.lower()
                    if k in self.mastered or any(x["spelling"].lower() == k for x in self.pool):
                        continue
                    self.pool.append({"spelling": w, "voc_id": "", "is_new": False,
                                      "source": "notepad", "local_meaning": ""})
                    try:
                        with open(WORDS_PATH, "a", encoding="utf-8") as f:
                            f.write("\n{} | (云词本导入)\n".format(w))
                    except Exception:
                        pass
                    added += 1
            return {"ok": True, "msg": "从云词本导入 {} 个单词".format(added), "total": len(self.pool)}
        except Exception as e:
            return {"ok": False, "msg": "导入失败: {}".format(e)}

    def add_word(self, spelling):
        spelling = (spelling or "").strip()
        if not spelling or not re.fullmatch(r"[A-Za-z][A-Za-z'\- ]*", spelling):
            return {"ok": False, "msg": "请输入正确的英文单词"}
        key = spelling.lower()
        if any(w["spelling"].lower() == key for w in self.pool):
            return {"ok": False, "msg": "这个词已经在列表里了"}
        msg = "已加入本地词表"
        cfg = load_config()
        tok = (cfg.get("token") or "").strip()
        if tok and cfg.get("use_api", True):
            try:
                vid = api_voc_id(spelling)
                if vid:
                    n = api_add_words([vid], advance=False)
                    msg = ("已加入本地词表并同步到墨墨账号" if n
                           else "已加入本地词表(墨墨:数量上限或已添加过,未同步)")
                else:
                    msg = "已加入本地词表(墨墨查无此词,未同步)"
            except Exception as e:
                msg = "已加入本地词表(墨墨同步失败:{})".format(e)
        try:
            with open(WORDS_PATH, "a", encoding="utf-8") as f:
                f.write("\n{} | (桌面端添加)\n".format(spelling))
        except Exception:
            pass
        self.pool.append({"spelling": spelling, "voc_id": "", "is_new": True,
                          "source": "local", "local_meaning": ""})
        return {"ok": True, "msg": msg, "total": len(self.pool)}

    def save_cfg(self, patch):
        cfg = load_config()
        for k in ("token", "show_word_sec", "show_meaning_sec", "corner", "tts",
                  "use_api", "youdao_enrich", "auto_mode"):
            if k in patch:
                cfg[k] = patch[k]
        save_config(cfg)
        if patch.get("corner"):
            self.reposition()
        return {"ok": True}

    def set_size(self, w, h):
        try:
            self.win.resize(int(w), int(h))
        except Exception:
            pass
        self.reposition()
        return {"ok": True}

    def reposition(self):
        cfg = load_config()
        try:
            w, h = self.win.width, self.win.height
        except Exception:
            w, h = 400, 168
        position_for(self.win, cfg.get("corner", "bottom_right"), w, h)

    def quit(self):
        try:
            self.win.destroy()
        except Exception:
            os._exit(0)


# ---------------- 入口 ----------------
def main():
    try:
        _main()
    except Exception:
        import traceback
        try:
            with open(os.path.join(BASE_DIR, "error.log"), "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise


def _main():
    if not acquire_lock():
        print("lock busy, exit")
        return
    import webview
    print("INDEX:", INDEX_PATH, flush=True)
    kw = dict(width=400, height=168, frameless=True, on_top=True,
              easy_drag=False, shadow=False)
    try:
        window = webview.create_window("墨墨背单词", INDEX_PATH, transparent=True, **kw)
    except TypeError:
        window = webview.create_window("墨墨背单词", INDEX_PATH, **kw)
    print("window created", flush=True)
    api = Api(window)
    for _m in ("get_state", "get_words", "get_detail", "speak", "mark_mastered",
               "mark_vague", "mark_forget", "add_preview", "add_word", "import_notepads",
               "save_cfg", "set_size", "reposition", "quit"):
        window.expose(getattr(api, _m))
    print("exposed, starting...", flush=True)
    webview.start()
    print("start returned", flush=True)


if __name__ == "__main__":
    main()
