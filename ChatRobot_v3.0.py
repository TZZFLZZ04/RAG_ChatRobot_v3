"""Legacy compatibility entrypoint.

The project now runs as a FastAPI service. This file is kept so existing users
who look for the old entrypoint can quickly discover the new startup command.
"""

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    print("ChatRobot_v3 has been refactored into a FastAPI project.")
    print("Start the API with:")
    print("  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    print(f"Default document directory: {settings.raw_data_dir}")
    print(f"Default vector index directory: {settings.faiss_index_dir}")


if __name__ == "__main__":
    main()
