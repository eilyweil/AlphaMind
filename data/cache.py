"""本地文件缓存层。

用途：把 akshare 慢接口（快照/资金流等全市场拉取）的结果落盘缓存，
打开应用时直接读缓存秒开，避免每次等待网络请求。支持预置示例数据作为初始缓存。
"""
import os
import pickle

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")


def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.pkl")


def load(key: str):
    """读缓存，命中返回数据，未命中返回 None。"""
    p = _path(key)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "rb") as f:
            return pickle.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"[cache] load {key} 失败: {e}")
        return None


def save(key: str, data) -> None:
    """写缓存（非空才写，避免缓存失败结果）。"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_path(key), "wb") as f:
            pickle.dump(data, f)
    except Exception as e:  # noqa: BLE001
        print(f"[cache] save {key} 失败: {e}")


def clear(key: str = None) -> None:
    """清缓存：不传 key 清空全部，传 key 清单个。"""
    if key:
        p = _path(key)
        if os.path.exists(p):
            os.remove(p)
    else:
        if os.path.isdir(CACHE_DIR):
            for f in os.listdir(CACHE_DIR):
                if f.endswith(".pkl"):
                    os.remove(os.path.join(CACHE_DIR, f))
