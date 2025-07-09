import requests
import json
import os


CACHE_DIR = "./cache/"
if not os.path.exists(CACHE_DIR):
    os.mkdir(CACHE_DIR)
    print("Created ./cache/ directory")


def get_route_data(target_addr: str) -> str | None:
    cache_address = CACHE_DIR + target_addr.replace(".", "_")
    if os.path.exists(cache_address):
        print(f"Using cached response for: {target_addr}")
        with open(cache_address) as f:
            return f.read()
        
    url = "https://traceroute-online.com/trace"
    
    headers = {
        "accept": "*/*",
        "content-type": "multipart/form-data; boundary=----WebKitFormBoundaryPZvxAgX56AGMrdA3",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
    
    data = b"------WebKitFormBoundaryPZvxAgX56AGMrdA3\r\n"
    data += b"Content-Disposition: form-data; name=\"target\"\r\n\r\n"
    data += target_addr.encode() + b"\r\n"
    data += b"------WebKitFormBoundaryPZvxAgX56AGMrdA3\r\n"
    data += b"Content-Disposition: form-data; name=\"query_type\"\r\n\r\n"
    data += b"trace\r\n"
    data += b"------WebKitFormBoundaryPZvxAgX56AGMrdA3--\r\n"
    
    response = requests.post(url, headers=headers, data=data)
    
    if "<h3>Traceroute Error</h3>" in response.text:
        print(f"Cannot get tracing data for: {target_addr}")
        return
    
    with open(cache_address, "w") as f:
        f.write(response.text)
        print(f"Cached response to: {target_addr}")
    
    return response.text
    

def fetch_hostnames(string: str, _hostnames: list[str] = None) -> list[str]:
    hostname_init = '"hostname": '
    if _hostnames is None:
        _hostnames = []
        
    if hostname_init not in string:
        return _hostnames
    
    chopped, hostname_part = string.split(hostname_init, 1)
    hostname = hostname_part.split(",")[0][1:][:-1]
    _hostnames.append(hostname)
    
    string = string[(len(chopped) + len(hostname_init) + len(hostname) + 3):]
    return fetch_hostnames(string, _hostnames)


def parse_response(response: str) -> list[tuple[tuple[float, float], str]]:
    locations = json.loads(response.split('"traceCoordinates": ')[1].split(', "traceMarkers"')[0])
    hostnames = fetch_hostnames(response.split('"traceMarkers": ')[1].split(";\n")[0][:-1])
    
    points = []
    for loc, hname in zip(locations, hostnames):
        points.append((
            (loc["lat"], loc["lng"]), hname
        ))

    return points
