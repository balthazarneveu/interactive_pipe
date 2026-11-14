"""Detection overlay: threshold + connected components on noisy blobs, scored against the ground truth.

What to look at: green boxes are true positives, red boxes false positives (noise specks, merged
blobs), yellow circles are missed blobs. Lower the threshold and the faint blobs appear but so does
noise; raise the minimal area to remove the specks. Precision / recall sum it up; the table lists
every detection with its area and peak intensity.
"""

from typing import Annotated

import numpy as np

from interactive_pipe import Table, draw, interactive, interactive_pipeline

RNG = np.random.default_rng(3)
CENTERS = RNG.uniform(16, 240, size=(14, 2))  # ground-truth blob centres (x, y)
AMPLITUDES = RNG.uniform(0.15, 0.8, size=14)


def make_image(n=256):
    y, x = np.mgrid[0:n, 0:n]
    img = sum(a * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / 80) for (cx, cy), a in zip(CENTERS, AMPLITUDES))
    return np.clip(0.1 + img + 0.06 * RNG.standard_normal((n, n)), 0, 1)


def label(mask):
    """4-connected components (numpy + a Python flood fill, no scipy): list of (ys, xs) per component."""
    seen, comps = np.zeros_like(mask), []
    for start in zip(*np.nonzero(mask)):
        if seen[start]:
            continue
        stack, pix = [start], []
        seen[start] = True
        while stack:
            y, x = stack.pop()
            pix.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        comps.append(tuple(np.array(pix).T))
    return comps


@interactive
def detect(
    img,
    threshold: Annotated[float, (0.0, 1.0), "Threshold"] = 0.25,
    min_area: Annotated[int, (1, 100), "Min area (px)"] = 20,
):
    comps = [c for c in label(img > threshold) if len(c[0]) >= min_area]
    detections = [
        dict(box=(xs.min(), ys.min(), xs.max(), ys.max()), area=len(xs), peak=img[ys, xs].max()) for ys, xs in comps
    ]
    return (detections,)  # a bare list would be read as one output per element


@interactive
def score(img, detections, max_dist: Annotated[float, (1.0, 15.0), "Match radius (px)"] = 6.0):
    centers = np.array(
        [[(d["box"][0] + d["box"][2]) / 2, (d["box"][1] + d["box"][3]) / 2] for d in detections]
    ).reshape(-1, 2)
    dist = np.linalg.norm(centers[:, None] - CENTERS[None], axis=-1)  # detections x ground truth
    tp = dist.min(axis=1, initial=np.inf) < max_dist
    found = dist.min(axis=0, initial=np.inf) < max_dist
    overlay = draw.boxes(
        img,
        [d["box"] for d in detections],
        labels=[str(i) for i in range(len(detections))],
        color=["lime" if t else "red" for t in tp],
    )
    overlay = draw.points(overlay, CENTERS[~found], color="yellow", radius=6, filled=False)
    precision = tp.mean() if len(tp) else 0.0
    rows = [
        dict(id=i, x=d["box"][0], y=d["box"][1], area=d["area"], peak=d["peak"], match=bool(t))
        for i, (d, t) in enumerate(zip(detections, tp))
    ]
    return overlay, Table(rows, title="detections"), f"precision {precision:.2f}   recall {found.mean():.2f}"


@interactive_pipeline(gui="auto")
def blob_detection(img):
    detections = detect(img)
    overlay, table, metrics = score(img, detections)
    return [[img, overlay], [table, metrics]]


if __name__ == "__main__":
    blob_detection(make_image())
