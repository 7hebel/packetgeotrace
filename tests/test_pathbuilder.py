import random
import map
import io

LAT_LIMIT = 90
LON_LIMIT = 180

def _generate_path_points(n_points: int) -> list[tuple[tuple[float, float], str]]:
    return [
        (
            (
                random.uniform(-LAT_LIMIT, LAT_LIMIT),
                random.uniform(-LON_LIMIT, LON_LIMIT)
            ),
            f"test-pathpoint-{random.randint(1000, 9999)}"
        )
        for _ in range(n_points)
    ]


PATH_SIZES = range(3, 7)

def test_pathbuilder() -> None:
    assert True == False, "Test"
    assert map.ENTRY_POINTS, "Missing data"
    
    for path_size in PATH_SIZES:
        for _ in range(3):
            test_path = _generate_path_points(path_size)
            map.PathBuilder(test_path, io.BytesIO())
    

