"""WolvenKit CR2W-JSON helpers: string swaps and the small resources generated in code."""
import base64
import json
from pathlib import Path

WK_JSON_HEADER = {"WolvenKitVersion": "9.1.0", "WKitJsonVersion": "0.0.9", "GameVersion": 2310,
                  "ExportedDateTime": "2026-01-01T00:00:00Z", "DataType": "CR2W", "ArchiveFileName": ""}


def iter_strings(obj):
    """Yield every string value in a serialized tree (iterative: animgraphs nest past the recursion limit)."""
    stack = [obj]
    while stack:
        node = stack.pop()
        for v in (node.values() if isinstance(node, dict) else node):
            if isinstance(v, str):
                yield v
            elif isinstance(v, (dict, list)):
                stack.append(v)


def swap(obj, pairs):
    """Replace exact string values anywhere in a serialized tree, in place."""
    stack = [obj]
    while stack:
        node = stack.pop()
        items = node.items() if isinstance(node, dict) else enumerate(node)
        for k, v in items:
            if isinstance(v, str):
                if v in pairs:
                    node[k] = pairs[v]
            elif isinstance(v, (dict, list)):
                stack.append(v)
    return obj


def renumber_handles(doc):
    """Close gaps in HandleId numbering (keeping WolvenKit's order) and update HandleRefIds to match."""
    nodes = []
    stack = [doc]
    while stack:
        node = stack.pop()
        if isinstance(node, dict) and ("HandleId" in node or "HandleRefId" in node):
            nodes.append(node)
        if isinstance(node, (dict, list)):
            stack.extend(node.values() if isinstance(node, dict) else node)
    old = sorted({int(n["HandleId"]) for n in nodes if "HandleId" in n})
    new = {str(o): str(i) for i, o in enumerate(old)}
    for n in nodes:
        key = "HandleId" if "HandleId" in n else "HandleRefId"
        n[key] = new[n[key]]
    return doc


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def wrap(root_chunk):
    return {"Header": dict(WK_JSON_HEADER),
            "Data": {"Version": 195, "BuildVersion": 0, "RootChunk": root_chunk, "EmbeddedFiles": []}}


def cname(s):
    return {"$type": "CName", "$storage": "string", "$value": s}


def res(path, flags="Soft"):
    if not path:
        return {"DepotPath": {"$type": "ResourcePath", "$storage": "uint64", "$value": "0"}, "Flags": flags}
    return {"DepotPath": {"$type": "ResourcePath", "$storage": "string", "$value": path}, "Flags": flags}


def localization(entries):
    """entries: {secondaryKey: text} -> onscreens JsonResource."""
    return wrap({
        "$type": "JsonResource",
        "cookingPlatform": "PLATFORM_PC",
        "root": {"HandleId": "0", "Data": {
            "$type": "localizationPersistenceOnScreenEntries",
            "entries": [{"$type": "localizationPersistenceOnScreenEntry", "femaleVariant": text,
                         "maleVariant": "", "primaryKey": "0", "secondaryKey": key}
                        for key, text in entries.items()]}},
    })


def inkatlas(texture, texture_1080, size, parts):
    """parts: {partName: (left, top, right, bottom)} in pixels of the full-size texture."""
    w, h = size

    def mapper(name, box):
        l, t, r, b = box
        return {"$type": "inkTextureAtlasMapper",
                "clippingRectInPixels": {"$type": "Rect", "bottom": b, "left": l, "right": r, "top": t},
                "clippingRectInUVCoords": {"$type": "RectF", "Bottom": b / h, "Left": l / w,
                                           "Right": r / w, "Top": t / h},
                "partName": cname(name)}

    def slot(tex, slot_parts):
        return {"$type": "inkTextureSlot", "parts": slot_parts, "slices": [], "texture": res(tex)}

    return wrap({
        "$type": "inkTextureAtlas",
        "activeTexture": "StaticTexture",
        "cookingPlatform": "PLATFORM_None",
        "dynamicTexture": res(None),
        "dynamicTextureSlot": {"$type": "inkDynamicTextureSlot", "parts": [], "texture": res(None)},
        "isSingleTextureMode": 1,
        "parts": [],
        "slices": [],
        "slots": {"Elements": [slot(texture, [mapper(n, b) for n, b in parts.items()]),
                               slot(texture_1080, []),
                               slot(None, [])]},
        "texture": res(None),
        "textureResolution": "UltraHD_3840_2160",
    })


def xbm_bc3(width, height, data):
    """A UI CBitmapTexture holding one BC3 (DXT5) mip."""
    assert width % 4 == 0 and height % 4 == 0 and len(data) == width * height
    row_pitch = width // 4 * 16
    return wrap({
        "$type": "CBitmapTexture",
        "cookingPlatform": "PLATFORM_PC",
        "depth": 1,
        "height": height,
        "histBiasAddCoef": {"$type": "Vector3", "X": 0, "Y": 0, "Z": 0},
        "histBiasMulCoef": {"$type": "Vector3", "X": 1, "Y": 1, "Z": 1},
        "renderResourceBlob": None,
        "renderTextureResource": {"$type": "rendRenderTextureResource", "renderResourceBlobPC": {
            "HandleId": "0", "Data": {
                "$type": "rendRenderTextureBlobPC",
                "header": {
                    "$type": "rendRenderTextureBlobHeader",
                    "flags": 1,
                    "histogramData": [],
                    "mipMapInfo": [{"$type": "rendRenderTextureBlobMipMapInfo",
                                    "layout": {"$type": "rendRenderTextureBlobMemoryLayout",
                                               "rowPitch": row_pitch, "slicePitch": len(data)},
                                    "placement": {"$type": "rendRenderTextureBlobPlacement",
                                                  "offset": 0, "size": len(data)}}],
                    "sizeInfo": {"$type": "rendRenderTextureBlobSizeInfo", "depth": 1,
                                 "height": height, "width": width},
                    "textureInfo": {"$type": "rendRenderTextureBlobTextureInfo", "dataAlignment": 8,
                                    "mipCount": 1, "sliceCount": 1, "sliceSize": len(data),
                                    "textureDataSize": len(data), "type": "TEXTYPE_2D"},
                    "version": 2,
                },
                "textureData": {"BufferId": "0", "Flags": 131072,
                                "Bytes": base64.b64encode(data).decode("ascii")},
            }}},
        "setup": {"$type": "STextureGroupSetup", "allowTextureDowngrade": 0, "alphaToCoverageThreshold": 0,
                  "compression": "TCM_DXTAlpha", "group": "TEXG_Generic_UI", "hasMipchain": 0, "isGamma": 1,
                  "isStreamable": 0, "platformMipBiasConsole": 0, "platformMipBiasPC": 0,
                  "rawFormat": "TRF_TrueColor"},
        "width": width,
    })
