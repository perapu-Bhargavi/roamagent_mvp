from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException
from pathlib import Path
import json

app = FastAPI(title="TBS RoamAgent")
app.mount("/static", StaticFiles(directory="static"), name="static")
# Load the sample transport dataset.
DATA_FILE = Path(__file__).parent / "data" / "routes.json"

with open(DATA_FILE, "r", encoding="utf-8") as file:
    ROUTES = json.load(file)["routes"]


def to_minutes(time_string):
    """Convert HH:MM into minutes after midnight."""
    hour, minute = map(int, time_string.split(":"))
    return hour * 60 + minute


def format_duration(minutes):
    """Format journey duration as hours and minutes."""
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


def find_journeys(origin, destination, minimum_transfer=30):
    """Find direct and one-connection journeys."""
    journeys = []

    origin = origin.strip().lower()
    destination = destination.strip().lower()

    # Find direct services.
    for route in ROUTES:
        if (
            route["from"].strip().lower() == origin
            and route["to"].strip().lower() == destination
        ):
            departure = to_minutes(route["departure"])
            arrival = to_minutes(route["arrival"])

            if arrival <= departure:
                arrival += 1440

            journeys.append({
                "legs": [route],
                "fare": route["fare"],
                "departure": route["departure"],
                "arrival": route["arrival"],
                "duration_minutes": arrival - departure,
                "transfer_minutes": 0,
                "transfers": 0
            })

    # Find journeys involving one connection.
    for first in ROUTES:
        if first["from"].strip().lower() != origin:
            continue

        for second in ROUTES:
            if first["to"].strip().lower() != second["from"].strip().lower():
                continue

            if second["to"].strip().lower() != destination:
                continue

            first_departure = to_minutes(first["departure"])
            first_arrival = to_minutes(first["arrival"])
            second_departure = to_minutes(second["departure"])
            second_arrival = to_minutes(second["arrival"])

            # Handle services that cross midnight.
            if first_arrival <= first_departure:
                first_arrival += 1440

            if second_departure <= first_departure:
                second_departure += 1440
                second_arrival += 1440

            if second_arrival <= second_departure:
                second_arrival += 1440

            while second_departure < first_arrival:
                second_departure += 1440
                second_arrival += 1440

            transfer_time = second_departure - first_arrival

            if transfer_time < minimum_transfer:
                continue

            journeys.append({
                "legs": [first, second],
                "fare": first["fare"] + second["fare"],
                "departure": first["departure"],
                "arrival": second["arrival"],
                "duration_minutes": second_arrival - first_departure,
                "transfer_minutes": transfer_time,
                "transfers": 1
            })

    # Remove duplicate journeys and rank by fare, then duration.
    unique_journeys = {}

    for journey in journeys:
        key = tuple(leg["id"] for leg in journey["legs"])
        unique_journeys[key] = journey

    return sorted(
        unique_journeys.values(),
        key=lambda journey: (
            journey["fare"],
            journey["duration_minutes"]
        )
    )


from fastapi.responses import FileResponse

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/routes")
def get_routes():
    return {
        "count": len(ROUTES),
        "routes": ROUTES
    }


@app.get("/plan")
def plan_trip(
    origin: str,
    destination: str,
    budget: int = 10000
):
    if not origin.strip() or not destination.strip():
        raise HTTPException(
            status_code=400,
            detail="Origin and destination are required."
        )

    if origin.strip().lower() == destination.strip().lower():
        raise HTTPException(
            status_code=400,
            detail="Origin and destination must be different."
        )

    if budget < 0:
        raise HTTPException(
            status_code=400,
            detail="Budget cannot be negative."
        )

    journeys = find_journeys(origin, destination)

    affordable = [
        journey for journey in journeys
        if journey["fare"] <= budget
    ]

    results = []

    for index, journey in enumerate(affordable, start=1):
        results.append({
            "option": index,
            "legs": journey["legs"],
            "fare": journey["fare"],
            "departure": journey["departure"],
            "arrival": journey["arrival"],
            "duration": format_duration(
                journey["duration_minutes"]
            ),
            "transfer_count": journey["transfers"],
            "transfer_minutes": journey["transfer_minutes"]
        })

    return {
        "origin": origin,
        "destination": destination,
        "count": len(results),
        "sorted_by": "lowest fare first",
        "message": (
            "Journeys found."
            if results
            else "No feasible journeys found within your budget."
        ),
        "journeys": results
    }
from pydantic import BaseModel


class DisruptionRequest(BaseModel):
    route_id: str
    delay_minutes: int = 120
    budget: int = 10000


@app.post("/disrupt")
def simulate_disruption(request: DisruptionRequest):
    if request.delay_minutes < 0:
        raise HTTPException(
            status_code=400,
            detail="Delay cannot be negative."
        )

    affected_route = next(
        (
            route for route in ROUTES
            if route["id"] == request.route_id
        ),
        None
    )

    if affected_route is None:
        raise HTTPException(
            status_code=404,
            detail="Route ID not found."
        )

    delayed_arrival = (
        to_minutes(affected_route["arrival"])
        + request.delay_minutes
    )

    delayed_arrival_text = (
        f"{(delayed_arrival // 60) % 24:02d}:"
        f"{delayed_arrival % 60:02d}"
    )

    alternatives = find_journeys(
        affected_route["from"],
        affected_route["to"]
    )

    alternatives = [
        journey for journey in alternatives
        if journey["fare"] <= request.budget
        and any(
            leg["id"] != affected_route["id"]
            for leg in journey["legs"]
        )
    ]

    return {
        "disruption": {
            "route_id": affected_route["id"],
            "from": affected_route["from"],
            "to": affected_route["to"],
            "original_arrival": affected_route["arrival"],
            "delay_minutes": request.delay_minutes,
            "simulated_arrival": delayed_arrival_text
        },
        "alternatives_found": len(alternatives),
        "alternatives": [
            {
                "route_ids": [
                    leg["id"] for leg in journey["legs"]
                ],
                "fare": journey["fare"],
                "departure": journey["departure"],
                "arrival": journey["arrival"],
                "duration": format_duration(
                    journey["duration_minutes"]
                )
            }
            for journey in alternatives
        ],
        "message": (
            "Alternative journeys found."
            if alternatives
            else "No alternative journeys found within your budget."
        ),
        "booking_status": "No booking has been made."
    }