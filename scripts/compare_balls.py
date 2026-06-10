"""Detecta los centros de las 4 bolas azules en dos imagenes y compara."""
from __future__ import annotations

import sys
import numpy as np
from PIL import Image


def blue_mask(arr: np.ndarray) -> np.ndarray:
    r = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    b = arr[:, :, 2].astype(int)
    # Azul saturado: B alto, R y G bajos.
    return (b > 120) & (r < 110) & (g < 110) & (b - r > 60) & (b - g > 60)


def cluster_centroids(mask: np.ndarray, expected: int = 4):
    ys, xs = np.where(mask)
    pts = list(zip(xs.tolist(), ys.tolist()))
    visited = [False] * len(pts)
    index = {}
    for i, (x, y) in enumerate(pts):
        index[(x, y)] = i
    clusters = []
    for i in range(len(pts)):
        if visited[i]:
            continue
        stack = [i]
        visited[i] = True
        comp = []
        while stack:
            j = stack.pop()
            x, y = pts[j]
            comp.append((x, y))
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    k = index.get((x + dx, y + dy))
                    if k is not None and not visited[k]:
                        visited[k] = True
                        stack.append(k)
        clusters.append(comp)
    clusters.sort(key=len, reverse=True)
    clusters = clusters[:expected]
    cents = []
    for comp in clusters:
        cx = sum(p[0] for p in comp) / len(comp)
        cy = sum(p[1] for p in comp) / len(comp)
        cents.append((round(cx, 1), round(cy, 1)))
    cents.sort(key=lambda c: (round(c[0] / 30), c[1]))  # ordenar por columnas, luego fila
    return cents


def detect(path: str):
    arr = np.array(Image.open(path).convert("RGB"))
    m = blue_mask(arr)
    return cluster_centroids(m, 4)


if __name__ == "__main__":
    orig, port = sys.argv[1], sys.argv[2]
    co = detect(orig)
    cp = detect(port)
    print("ORIGINAL centroids:", co)
    print("PORT     centroids:", cp)
    # Emparejar por cercania (greedy).
    print("\nBall | orig(x,y) | port(x,y) | dx | dy")
    used = [False] * len(cp)
    maxd = 0.0
    for i, (ox, oy) in enumerate(co):
        best, bj = 1e9, -1
        for j, (px, py) in enumerate(cp):
            if used[j]:
                continue
            d = (ox - px) ** 2 + (oy - py) ** 2
            if d < best:
                best, bj = d, j
        px, py = cp[bj]
        used[bj] = True
        dx, dy = px - ox, py - oy
        maxd = max(maxd, abs(dx), abs(dy))
        print(f"{i+1:>4} | ({ox:.1f},{oy:.1f}) | ({px:.1f},{py:.1f}) | {dx:+.1f} | {dy:+.1f}")
    print(f"\nMax abs component diff: {maxd:.1f}px")
    print("VERDICT:", "PASS (<=3px)" if maxd <= 3.0 else "CHECK (>3px)")
