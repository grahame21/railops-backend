import json, datetime

OUT_FILE = "trains.json"

def main():
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "trains": [
            {"id": "TEST1", "lat": -34.9285, "lon": 138.6007, "operator": "TEST"},
            {"id": "TEST2", "lat": -37.8136, "lon": 144.9631, "operator": "TEST"},
        ],
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    print("Updated trains.json")

if __name__ == "__main__":
    main()
