from tracing import traceapi, routetrace
from map import PathBuilder

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi import FastAPI
from io import BytesIO
import uvicorn

api = FastAPI()
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/trace/{trace_type}/{target_url}")
async def trace(trace_type: str, target_url: str) -> Response:
    if trace_type == "local":
        return trace_from_local(target_url)
    if trace_type == "external":
        return trace_by_api(target_url)
    return Response(f"Invalid trace_type: {trace_type}")
    
    
def _build_map(points: list[tuple[tuple[float, float], str]]) -> Response:
    html_out = BytesIO()
    PathBuilder(points, html_out)

    html_out.seek(0)
    map_data = html_out.read().decode()
    return Response(map_data)

    
def trace_from_local(target_url: str) -> Response:
    try:
        route_data = routetrace.RouteTracer(target_url).trace_route()
    except:
        return Response("Invalid address or failed to generate map.")

    points = [
        (
            (point["lat"], point["lon"]), 
            point["host"] or point["ip"]
        ) for point in route_data if point["lat"]
    ]
    
    return _build_map(points)

def trace_by_api(target_url: str) -> Response:
    data = traceapi.get_route_data(target_url)
    if not data:
        return Response("Invalid address or failed to generate map.")

    points = traceapi.parse_response(data)

    return _build_map(points)

uvicorn.run(api, port=8084)
