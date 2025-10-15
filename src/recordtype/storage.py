import os, json, datetime as dt, shutil, sys, platform

# ---------- 路径 ----------
def _user_data_root():
    # 跨平台用户数据目录
    if platform.system() == "Windows":
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "RecordType")
    else:
        base = os.path.expanduser("~/.local/share")
        return os.path.join(base, "RecordType")

def ensure_user_data_dir():
    p = _user_data_root()
    os.makedirs(p, exist_ok=True)
    return p

def recent_json_path():
    return os.path.join(ensure_user_data_dir(), "recent_sessions.json")

# ---------- 会话目录 ----------
def default_sessions_root():
    # 建议统一存到 文档/RecordTypeSessions；若没权限退回当前目录
    try:
        doc = os.path.join(os.path.expanduser("~"), "Documents")
        p = os.path.join(doc, "RecordTypeSessions")
        os.makedirs(p, exist_ok=True)
        return p
    except Exception:
        return os.getcwd()

def new_session_dir(base_dir=None):
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = base_dir or default_sessions_root()
    path = os.path.abspath(os.path.join(root, f"session_{ts}"))
    os.makedirs(path, exist_ok=True)
    return path

# ---------- 基础 IO ----------
def save_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def export_dir(src, dst_dir):
    base = os.path.basename(src)
    target = os.path.join(dst_dir, base)
    if os.path.exists(target):
        raise FileExistsError("目标已存在同名文件夹")
    shutil.copytree(src, target)
    return target

# ---------- 最近会话 ----------
def load_recent(limit=200):
    p = recent_json_path()
    if not os.path.exists(p):
        return []
    try:
        arr = json.load(open(p, "r", encoding="utf-8"))
        # 只保留存在的目录
        arr = [x for x in arr if os.path.isdir(x)]
        return arr[:limit]
    except Exception:
        return []

def add_recent(session_dir, limit=200):
    arr = load_recent(limit*2)
    # 去重：本次优先
    arr = [session_dir] + [x for x in arr if x != session_dir]
    save_json(recent_json_path(), arr[:limit])

def remove_recent(session_dir):
    arr = load_recent()
    arr = [x for x in arr if x != session_dir]
    save_json(recent_json_path(), arr)
