
import numpy as np


def make_heatmap(temps_c):
    grid = np.array(temps_c, dtype=float)

    if grid.ndim != 2 or grid.size < 2:
        raise ValueError("Temperature grid must be 2-D (any size, e.g. 2x4)")

    if not np.isfinite(grid).all():
        raise ValueError("Temperature values must be finite")

    median = np.median(grid)

    differences = np.maximum(grid - median, 0)

    maximum = differences.max()

    if maximum == 0:
        return np.zeros(grid.shape).tolist()

    heatmap = differences / maximum

    return np.round(heatmap, 2).tolist()


if __name__ == "__main__":
    sample = [
        [41.2, 41.5, 41.0],
        [41.3, 47.9, 41.1]
    ]

    print("Temperature grid:")
    print(sample)

    print("\nGenerated heatmap:")
    print(make_heatmap(sample))
