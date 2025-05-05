name: Refresh TrainFinder Cookie

on:
  schedule:
    - cron: '0 16 * * *'  # Every day at 2:30 AM Adelaide time
  workflow_dispatch:

jobs:
  refresh-cookie:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: pip install selenium

    - name: Run TrainFinder login script
      env:
        TRAINFINDER_USERNAME: ${{ secrets.TRAINFINDER_USERNAME }}
        TRAINFINDER_PASSWORD: ${{ secrets.TRAINFINDER_PASSWORD }}
      run: |
        python trainfinder_login.py
        echo "COOKIE_VALUE=$(<cookie.txt)" >> $GITHUB_ENV

    - name: Upload cookie to GitHub Secret (manual step still required)
      run: echo "::warning::Cookie written to GITHUB_ENV — use gh CLI or actions/github-script to upload"
