from pydantic import BaseSettings, AnyHttpUrl
from typing import Optional

class Settings(BaseSettings):
    # The FULL TrainFinder data URL (exactly as captured in your browser’s Network tab)
    # Example: https://trainfinder.otenko.com/Home/GetViewPortData?something=...
    TRAINFINDER_VIEWPORT_URL: AnyHttpUrl

    # Your .ASPXAUTH cookie value (no quotes, just the value)
    TRAINFINDER_ASPXAUTH: str

    # Optional proxy (e.g. http://username:password@au.proxymesh.com:31280)
    HTTP_PROXY_URL: Optional[str] = None

    # Update interval seconds
    UPDATE_INTERVAL: int = 30

    # Server host/port (Render will override, but useful locally)
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()
