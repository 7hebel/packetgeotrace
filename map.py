import folium
import math
import json
import time


GROUND_EXCHANGE_TYPE = "ground-exchange"
SUBMARINE_TYPE = "submarine"
CABLE_BREAK_LEN = 10


# Load infrastructure data
INFRASTRUCTURE_POINTS: dict[tuple[float, float], dict] = {}

with open("data/ground-exchange.json") as ground_exchange_file:
    ground_ex_data = json.load(ground_exchange_file)
    for ex_point_name, ex_point_loc in ground_ex_data.items():
        INFRASTRUCTURE_POINTS[tuple(ex_point_loc)] = {
            "type": GROUND_EXCHANGE_TYPE,
            "data": ex_point_name
        }

with open("data/submarine.json") as submarine_file:
    SUBMARINE_CABLES = json.load(submarine_file)
    for cable in SUBMARINE_CABLES:
        if len(cable["endpoints"]) == 1:
            continue

        for cable_endpoint in cable["endpoints"]:
            INFRASTRUCTURE_POINTS[tuple(cable_endpoint)] = {
                "type": SUBMARINE_TYPE,
                "data": cable
            }


class PathBuilder:
    def __init__(self, path_points: list[tuple[tuple[float, float], str]], output_file: str) -> None:
        build_start_time = time.time_ns()
        self.map = folium.Map()

        # Add markers to the signal points.
        for index, (loc, name) in enumerate(path_points, 1):
            folium.Marker(self.find_closest_point(loc, INFRASTRUCTURE_POINTS), f"({index}) {name}").add_to(self.map)

        # Connect subsequent points.
        for i in range(len(path_points)-1):
            start = self.find_closest_point(path_points[i][0], INFRASTRUCTURE_POINTS)
            end = self.find_closest_point(path_points[i+1][0], INFRASTRUCTURE_POINTS)
            self.build_path_between(start, end)

        self.map.save(output_file, close_file=False)
        print(f"Built map in: {(time.time_ns() - build_start_time) / 1_000_000_000}s ({output_file})")

    def load_submarine_entries(self) -> dict[tuple[float, float], list[dict]]:
        """
        Parse submarine cables stored in points register.
        Create map of all entries for faster cable lookups.
        """
        submarine_entries = {}

        for point in INFRASTRUCTURE_POINTS.values():
            point_data = point["data"]
            if point["type"] != SUBMARINE_TYPE:
                continue

            for endpoint in point_data["endpoints"]:
                endpoint = tuple(endpoint)

                if endpoint not in submarine_entries:
                    submarine_entries[endpoint] = []
                submarine_entries[endpoint].append(point_data)

        return submarine_entries

    def find_closest_point(self, target_loc: tuple[float, float], positions: list[tuple[float, float]]) -> tuple[float, float]:
        """ Returns point closest to the target location from list of points. """
        closest_dist = None
        closest_point = None

        for pos in positions:
            distance = math.dist(pos, target_loc)
            if closest_dist is None or distance < closest_dist:
                closest_dist = distance
                closest_point = pos

        return tuple(closest_point)

    def find_closest_submarine_cable_between(self, start_loc: tuple[float, float], end_loc: tuple[float, float]) -> tuple[tuple[float, float], dict]:
        cables_distance_to_entry = []

        for cable in SUBMARINE_CABLES:
            closest_entry = self.find_closest_point(start_loc, cable["endpoints"])
            distance_to_entry = math.dist(start_loc, closest_entry)
            cables_distance_to_entry.append((distance_to_entry, cable))
        
        min_path_distance = None
        closest_cable = None

        for (entry_distance, cable) in cables_distance_to_entry:
            for endpoint_loc in cable["endpoints"]:
                endpoint_distance = math.dist(endpoint_loc, end_loc)
                total_distance = entry_distance + endpoint_distance + (0.5 * math.dist((entry_distance,), (endpoint_distance,)))
        
                if min_path_distance is None or total_distance < min_path_distance:
                    min_path_distance = total_distance
                    closest_cable = cable
                
        return (min_path_distance, closest_cable)

    def draw_ground_line(self, start_loc: tuple[float, float], end_loc: tuple[float, float], _no_break: bool = False) -> None:
        if math.dist(start_loc, end_loc) > CABLE_BREAK_LEN and not _no_break:
            return self.break_path(start_loc, end_loc)

        folium.PolyLine([start_loc, end_loc], color="red").add_to(self.map)

    def draw_submarine_cable(self, start_loc: tuple[float, float], end_loc: tuple[float, float], full_geometry: list[list[float, float]], name: str) -> None:
        geometry_start = full_geometry.index(list(self.find_closest_point(start_loc, full_geometry)))
        geometry_end = full_geometry.index(list(self.find_closest_point(end_loc, full_geometry)))
        if geometry_start > geometry_end:
            geometry_start, geometry_end = geometry_end, geometry_start

        geometry_slice = full_geometry[geometry_start:geometry_end + 1]
        folium.PolyLine(geometry_slice, name, color="blue", weight=3).add_to(self.map)

    def break_path(self, start_loc: tuple[float, float], end_loc: tuple[float, float]) -> None:
        """ 
        If the distance between two ground points is too long, break this path by adding point in the middle
        and connecting START->MID, MID->END (theese connections might also be broken into shorter ones).
        This approach provides higher path accuracy as it will include more shorter submarine routes.
        """
        mid_point = self.find_closest_point((
            (start_loc[0]+end_loc[0])/2,
            (start_loc[1]+end_loc[1])/2
        ), INFRASTRUCTURE_POINTS)

        if mid_point in {start_loc, end_loc}:  # There is no available point between start and end.
            return self.draw_ground_line(start_loc, end_loc, _no_break=True)  

        self.build_path_between(start_loc, mid_point)
        self.build_path_between(mid_point, end_loc)

    def build_path_between(self, start_loc: tuple[float, float], end_loc: tuple[float, float]) -> list[dict]:
        start_data = INFRASTRUCTURE_POINTS[start_loc]["data"]
        start_type = INFRASTRUCTURE_POINTS[start_loc]["type"]
        end_data = INFRASTRUCTURE_POINTS[end_loc]["data"]
        end_type = INFRASTRUCTURE_POINTS[end_loc]["type"]

        if start_type == end_type == GROUND_EXCHANGE_TYPE:
            self._ground_to_ground(start_loc, end_loc)

        if start_type == end_type == SUBMARINE_TYPE:
            self._submarine_to_submarine(start_loc, start_data, end_loc, end_data)

        if start_type == GROUND_EXCHANGE_TYPE and end_type == SUBMARINE_TYPE:
            self._ground_to_submarine(start_loc, end_loc, end_data)

        if start_type == SUBMARINE_TYPE and end_type == GROUND_EXCHANGE_TYPE:
            self._submarine_to_ground(start_loc, start_data, end_loc)

    def _ground_to_ground(self, start_loc: tuple[float, float], end_loc: tuple[float, float]) -> None:
        ground_distance = math.dist(start_loc, end_loc)
        water_distance, closest_cable = self.find_closest_submarine_cable_between(start_loc, end_loc)

        if water_distance < ground_distance:
            closest_cable_entry = self.find_closest_point(start_loc, closest_cable["endpoints"])
            closest_cable_exit = self.find_closest_point(end_loc, closest_cable["endpoints"])

            self.draw_ground_line(start_loc, closest_cable_entry)
            self.draw_submarine_cable(closest_cable_entry, closest_cable_exit, closest_cable["geometry"], closest_cable["name"])
            return self.build_path_between(closest_cable_exit, end_loc)

        return self.draw_ground_line(start_loc, end_loc)

    def _submarine_to_ground(self, start_loc: tuple[float, float], start_data: dict, end_loc: tuple[float, float]) -> None:
        closest_cable_exit = self.find_closest_point(end_loc, start_data["endpoints"])
        if closest_cable_exit != start_loc:  # Submarine cable can transfer packet closer to the target.
            self.draw_submarine_cable(start_loc, closest_cable_exit, start_data["geometry"], start_data["name"])
            return self.build_path_between(closest_cable_exit, end_loc)

        self.draw_ground_line(start_loc, end_loc)

    def _ground_to_submarine(self, start_loc: tuple[float, float], end_loc: tuple[float, float], end_data: dict) -> None:
        closest_cable_entry = self.find_closest_point(start_loc, end_data["endpoints"])
        if closest_cable_entry == end_loc:
            return self.draw_ground_line(start_loc, end_loc)

        self.build_path_between(start_loc, closest_cable_entry)
        self.draw_submarine_cable(closest_cable_entry, end_loc, end_data["geometry"], end_data["name"])

    def _submarine_to_submarine(self, start_loc: tuple[float, float], start_data: dict, end_loc: tuple[float, float], end_data: dict) -> None:
        # The same cable.
        if end_loc in start_data["endpoints"]:
            return self.draw_submarine_cable(start_loc, end_loc, start_data["geometry"], start_data["name"])

        # Different cable.
        closest_endpoint = self.find_closest_point(end_loc, start_data["endpoints"])
        if closest_endpoint == start_loc:
            closest_entry = self.find_closest_point(start_loc, end_data["endpoints"])
            self.draw_ground_line(start_loc, closest_entry)

            if closest_entry != end_loc:
                self.draw_submarine_cable(closest_entry, end_loc, end_data["geometry"], end_data["name"])

        else:
            self.draw_submarine_cable(start_loc, closest_endpoint, start_data["geometry"], start_data["name"])
            return self.build_path_between(closest_endpoint, end_loc)
