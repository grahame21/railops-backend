from trainfinder_backend import update_local_file

if __name__ == "__main__":
    data = update_local_file(headless=True, preserve_last_good=True)
    print(f"✅ Fast scraper finished: {len(data.get('trains') or [])} trains | {data.get('note')}")
