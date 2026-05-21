import os

def show_banners() -> bool:
    env = os.getenv("ENVIRONMENT", "production").lower()
    banners = os.getenv("LOG_BANNERS", "false").lower()
    return env in ["development", "dev"] and banners == "true"