"""The nearest stored point within a tolerance (core/nearest.py) agrees
with a scan of all of them, one position at a time and in bulk."""
import time

import numpy as np

from guiqula.core.nearest import nearest_indices, nearest_site


def scan(points, r, tol):
    d = np.linalg.norm(np.asarray(points)[:, :3] - np.asarray(r), axis=1)
    i = int(np.argmin(d))
    return i if d[i] < tol else -1


def test_agrees_with_a_scan():
    rng = np.random.default_rng(3)
    points = rng.uniform(-5, 5, (400, 3))
    points[:, 2] = np.round(points[:, 2])            # layers
    points = np.vstack([points, points[:5]])        # duplicates: the lowest index wins
    queries = np.vstack([points + rng.normal(0, 0.03, points.shape),
                         rng.uniform(-6, 6, (300, 3))])
    for tol in (0.05, 0.3, 2.0):
        find = nearest_site(points, tol)
        expected = [scan(points, r, tol) for r in queries]
        assert [find(r) for r in queries] == expected
        assert nearest_indices(points, queries, tol).tolist() == expected
    assert nearest_indices(np.zeros((0, 3)), queries, 0.1).tolist() == [-1] * len(queries)
    assert nearest_site([], 0.1)((0, 0, 0)) == -1
    assert nearest_indices([[1.0, 2.0, 3.0, 9.0]], [[1.0, 2.0, 3.05]], 0.1).tolist() == [0]


def test_is_fast_for_many_sites():
    x, y = np.meshgrid(np.arange(150.0), np.arange(150.0))
    points = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])     # 22,500 sites
    start = time.perf_counter()
    found = nearest_indices(points, points[::-1], 0.05)
    assert time.perf_counter() - start < 1.0
    assert found.tolist() == list(range(len(points)))[::-1]
    far = nearest_indices(points, points * 1e6, 1e-3)                 # a large extent
    assert found[0] >= 0 and far[0] == 0 and far[1] == -1
