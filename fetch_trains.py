name: TrainFinder Fetch (every 5 min)

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: trainfinder-fetch
  cancel-in-progress: false

jobs:
  fetch:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          python -m playwright install --with-deps chromium

      - name: Login + fetch
        env:
          TRAINFINDER_USERNAME: ${{ secrets.TRAINFINDER_USERNAME }}
          TRAINFINDER_PASSWORD: ${{ secrets.TRAINFINDER_PASSWORD }}
        run: |
          echo "🚆 Running TrainFinder login_and_sweep.py"
          python scripts/login_and_sweep.py
          test -f trains.json && echo "✅ trains.json generated"

      - name: Commit trains.json if changed
        run: |
          git config user.name "github-actions"
          git config user.email "actions@users.noreply.github.com"
          git add trains.json
          if git diff --cached --quiet; then
            echo "No changes in trains.json"
          else
            git commit -m "Auto-update trains.json [skip ci]"
            git push
          fi
