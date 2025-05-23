import json
import os

# Dummy train data for testing
trains = [
    {"loco": "NR84", "lat": -33.86, "lon": 151.20},
    {"loco": "DL46", "lat": -34.92, "lon": 138.60}
]

# Make sure static/ exists
os.makedirs("static", exist_ok=True)

# Write trains.json
with open("static/trains.json", "w") as f:
    json.dump(trains, f)

print("Generated static/trains.json")