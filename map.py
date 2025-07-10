import folium
import math
import json
import time
import sys

GROUND_EXCHANGE_TYPE = "ground-exchange"
SUBMARINE_TYPE = "submarine"
ENTRY_POINTS: dict[tuple[float, float], dict] = {}
CABLE_BREAK_LEN = 10


with open("data/ground-exchange.json") as ground_exchange_file:
    ground_ex_data = json.load(ground_exchange_file)
    for ex_point_name, ex_point_loc in ground_ex_data.items():
        ENTRY_POINTS[tuple(ex_point_loc)] = {
            "type": GROUND_EXCHANGE_TYPE,
            "data": ex_point_name
        }

with open("data/submarine.json") as submarine_file:
    submarine_data = json.load(submarine_file)
    for cable in submarine_data:
        if len(cable["endpoints"]) == 1:
            continue
        
        for cable_endpoint in cable["endpoints"]:
            ENTRY_POINTS[tuple(cable_endpoint)] = {
                "type": SUBMARINE_TYPE,
                "data": cable
            }
    

class PathBuilder:
    def __init__(self, points: list[tuple[tuple[float, float], str]], output_file: str) -> None:
        self.points = points
        self.map = folium.Map()
        
        self.points_register = ENTRY_POINTS
        self.all_endpoints = list(self.points_register.keys())
        self.submarine_entries = self.get_submarine_entries()
        
        start_time = time.time_ns()
        self.add_markers_to_signal_points()

        for i in range(len(self.points)-1):
            start = self.find_closest_point(points[i][0], self.all_endpoints)
            end = self.find_closest_point(points[i+1][0], self.all_endpoints)
            self.build_path_between(start, end)
        
        self.map.save(output_file, False)
        print(f"Built map in: {(time.time_ns() - start_time)/1000000000}s ({output_file})")

    
    def get_submarine_entries(self) -> dict[tuple[float, float], list[dict]]:
        """
        Parse submarine cables stored in points register. 
        Create map of all entries for faster cable lookups.
        """
        submarine_entries = {}
        
        for point in self.points_register.values():
            if point["type"] != SUBMARINE_TYPE:
                continue
            
            point_data = point["data"]
            
            for endpoint in point_data["endpoints"]:
                endpoint = tuple(endpoint)
    
                if endpoint not in submarine_entries:
                    submarine_entries[endpoint] = []
                submarine_entries[endpoint].append(point_data)
        
        return submarine_entries

    def find_closest_point(self, target_loc: tuple[float, float], positions: list[tuple[float, float]]) -> tuple[float, float]:
        closest_dist = None
        closest_point = None
        
        for pos in positions:
            distance = math.dist(pos, target_loc)
            if closest_dist is None or distance < closest_dist:
                closest_dist = distance
                closest_point = pos
            
        return tuple(closest_point)  
    
    def find_closest_cable_between(self, start_loc: tuple[float, float], end_loc: tuple[float, float]) -> tuple[tuple[float, float], dict]:
        closest_to_start = []
        for entry_loc, cables in self.submarine_entries.items():
            distance_to_entry = math.dist(start_loc, entry_loc)
            for cable in cables:
                closest_to_start.append((distance_to_entry, cable))
        
        closest_to_start = list(sorted(closest_to_start, key=lambda i: i[0]))
        
        min_dist = None
        closest_cable = None
        for (entry_dist, cable) in closest_to_start:
            for endpoint_loc in cable["endpoints"]:
                endpoint_dist = math.dist(endpoint_loc, end_loc)
                total_dist = entry_dist + endpoint_dist + (0.5 * math.dist((entry_dist,), (endpoint_dist,)))
        
                if min_dist is None or total_dist < min_dist:
                    min_dist = total_dist
                    closest_cable = cable
                
        return (min_dist, closest_cable)
    
    def add_markers_to_signal_points(self) -> None:
        for index, (loc, name) in enumerate(self.points, 1):
            folium.Marker(self.find_closest_point(loc, self.all_endpoints), f"({index}) {name}").add_to(self.map)

    def draw_ground_line(self, start_loc: tuple[float, float], end_loc: tuple[float, float], _no_break: bool = False) -> None:
        if math.dist(start_loc, end_loc) > CABLE_BREAK_LEN and not _no_break:
            return self.break_path(start_loc, end_loc)
        
        folium.PolyLine([start_loc, end_loc], color="red").add_to(self.map)
        
    def draw_submarine_cable(self, start_loc: tuple[float, float], end_loc: tuple[float, float], full_geometry: list[list[float, float]], name: str) -> None:
        folium.PolyLine(full_geometry, name, color="blue", weight=3).add_to(self.map)
        folium.PolyLine([start_loc, end_loc], color="cyan", weight=1).add_to(self.map)
    
    def break_path(self, start_loc: tuple[float, float], end_loc: tuple[float, float]) -> None:
        mid_point = self.find_closest_point((
            (start_loc[0]+end_loc[0])/2,
            (start_loc[1]+end_loc[1])/2
        ), self.all_endpoints)

        if mid_point in {start_loc, end_loc}:
            return self.draw_ground_line(start_loc, end_loc, _no_break=True)  # There is no available point between start and end.

        self.build_path_between(start_loc, mid_point)
        self.build_path_between(mid_point, end_loc)
    
    def build_path_between(self, start_loc: tuple[float, float], end_loc: tuple[float, float]) -> list[dict]:
        start_data = self.points_register[start_loc]["data"]
        start_type = self.points_register[start_loc]["type"]
        end_data = self.points_register[end_loc]["data"]
        end_type = self.points_register[end_loc]["type"]
        
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
        water_distance, closest_cable = self.find_closest_cable_between(start_loc, end_loc)

        if water_distance < ground_distance:
            closest_cable_entry = self.find_closest_point(start_loc, closest_cable["endpoints"])
            closest_cable_exit = self.find_closest_point(end_loc, closest_cable["endpoints"])

            self.draw_ground_line(start_loc, closest_cable_entry)
            self.draw_submarine_cable(closest_cable_entry, closest_cable_exit, closest_cable["geometry"], closest_cable["name"])
            return self.build_path_between(closest_cable_exit, end_loc)
        
        return self.draw_ground_line(start_loc, end_loc)
        
    def _submarine_to_ground(self, start_loc: tuple[float, float], start_data: dict, end_loc: tuple[float, float]) -> None:
        closest_cable_endpoint = self.find_closest_point(end_loc, start_data["endpoints"])
        if closest_cable_endpoint != start_loc:  # Cable can transfer packet closer to the target.
            self.draw_submarine_cable(start_loc, closest_cable_endpoint, start_data["geometry"], start_data["name"])
            return self.build_path_between(closest_cable_endpoint, end_loc)

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
                # return self.build_path_between(closest_entry, end_loc)
                self.draw_submarine_cable(closest_entry, end_loc, end_data["geometry"], end_data["name"])
        
        else:
            self.draw_submarine_cable(start_loc, closest_endpoint, start_data["geometry"], start_data["name"])
            return self.build_path_between(closest_endpoint, end_loc)
