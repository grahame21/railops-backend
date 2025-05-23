import json
from datetime import datetime

# Dummy train data for now – replace this with real API calls
train_data = [
    {
        "loco": "NR74",
        "operator": "Pacific National",
        "location": "Adelaide SA",
        "lat": -34.9285,
        "lon": 138.6007,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
]

# Save to static/trains.json
with open("static/trains.json", "w") as f:
    json.dump(train_data, f, indent=2)