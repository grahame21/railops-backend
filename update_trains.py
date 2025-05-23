import json
import time
import requests

def fetch_train_data():
    # Replace this with actual logic to fetch real train data
    return [
        {"id": "NR84", "lat": -33.865, "lon": 151.209, "status": "on time"},
        {"id": "DL47", "lat": -34.9285, "lon": 138.6007, "status": "delayed"}
    ]

def main():
    train_data = fetch_train_data()
    Path("static").mkdir(exist_ok=True)
    with open("static/trains.json", "w") as f:
        json.dump(train_data, f, indent=2)

if __name__ == "__main__":
    main()
