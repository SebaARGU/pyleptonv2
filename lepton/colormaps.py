import numpy as np


COLORMAP_GRAYSCALE = 0
COLORMAP_IRONBLACK = 1
COLORMAP_RAINBOW = 2


def _build_grayscale():
    table = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        v = 255 - i
        table[i] = [v, v, v]
    return table


def _build_ironblack():
    table = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        if i < 128:
            v = int(255 - (i / 127) * 255)
            table[i] = [v, v, v]
        elif i < 160:
            f = (i - 128) / 31
            r = int(f * 150)
            g = 0
            b = int((1 - f) * 80)
            table[i] = [r, g, b]
        elif i < 192:
            f = (i - 160) / 31
            r = 150 + int(f * 105)
            g = int(f * 80)
            b = 0
            table[i] = [r, g, b]
        elif i < 224:
            f = (i - 192) / 31
            r = 255
            g = 80 + int(f * 175)
            b = 0
            table[i] = [r, g, b]
        else:
            f = (i - 224) / 31
            r = 255
            g = 255
            b = int(f * 200)
            table[i] = [r, g, b]
    return table


def _build_rainbow():
    table = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        if i < 42:
            f = i / 41
            table[i] = [int(f * 20), 0, 128 + int(f * 127)]
        elif i < 85:
            f = (i - 42) / 42
            table[i] = [0, int(f * 200), 255]
        elif i < 128:
            f = (i - 85) / 42
            table[i] = [0, 200 + int(f * 55), 255 - int(f * 255)]
        elif i < 170:
            f = (i - 128) / 41
            table[i] = [int(f * 200), 255, 0]
        elif i < 213:
            f = (i - 170) / 42
            table[i] = [200 + int(f * 55), 255 - int(f * 255), 0]
        else:
            f = (i - 213) / 42
            table[i] = [255, int((1 - f) * 100), 0]
    return table


_COLORMAPS = {
    COLORMAP_GRAYSCALE: _build_grayscale(),
    COLORMAP_IRONBLACK: _build_ironblack(),
    COLORMAP_RAINBOW: _build_rainbow(),
}

_COLORMAP_NAMES = {
    COLORMAP_GRAYSCALE: "Grayscale",
    COLORMAP_IRONBLACK: "Ironblack",
    COLORMAP_RAINBOW: "Rainbow",
}


def get_colormap(name_or_id):
    if isinstance(name_or_id, str):
        name_or_id = name_or_id.lower()
        for cid, cname in _COLORMAP_NAMES.items():
            if cname.lower() == name_or_id:
                return _COLORMAPS[cid]
        raise ValueError(f"Unknown colormap: {name_or_id}")
    return _COLORMAPS[name_or_id]


def apply_colormap(frame_8bit, colormap_id=COLORMAP_IRONBLACK):
    if frame_8bit.dtype != np.uint8:
        raise ValueError("frame_8bit must be uint8")

    cmap = _COLORMAPS[colormap_id]
    return cmap[frame_8bit]


def list_colormaps():
    return [(cid, name) for cid, name in _COLORMAP_NAMES.items()]


def colormap_name(cid):
    return _COLORMAP_NAMES.get(cid, "Unknown")
