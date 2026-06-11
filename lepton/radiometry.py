import numpy as np


def raw_to_celsius(raw_data):
    if raw_data.dtype != np.uint16:
        raise ValueError("raw_data must be uint16")

    kelvin = raw_data.astype(np.float32) / 100.0
    celsius = kelvin - 273.15

    return celsius


def get_frame_temperatures(celsius):
    valid = celsius[celsius > -273.15]
    if valid.size == 0:
        return {"min": float("nan"), "max": float("nan"),
                "avg": float("nan"), "min_pos": None, "max_pos": None}

    min_idx = np.unravel_index(np.argmin(celsius), celsius.shape)
    max_idx = np.unravel_index(np.argmax(celsius), celsius.shape)

    return {
        "min": float(valid.min()),
        "max": float(valid.max()),
        "avg": float(valid.mean()),
        "min_pos": min_idx,
        "max_pos": max_idx,
    }


def auto_range(raw_data, margin=500):
    valid = raw_data[raw_data > 0]
    if valid.size == 0:
        return 0, 65535

    vmin = int(valid.min())
    vmax = int(valid.max())

    if vmax - vmin < 100:
        vmin = max(0, vmin - margin // 2)
        vmax = min(65535, vmax + margin // 2)

    return vmin, vmax


def normalize_frame(raw_data, vmin=None, vmax=None):
    if vmin is None or vmax is None:
        vmin, vmax = auto_range(raw_data)
    if vmax == vmin:
        return np.zeros_like(raw_data, dtype=np.uint8)

    normalized = ((raw_data.astype(np.float32) - vmin) / (vmax - vmin) * 255)
    np.clip(normalized, 0, 255, out=normalized)
    return normalized.astype(np.uint8)
