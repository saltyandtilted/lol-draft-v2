"""Start the development server on port 5001 (port 5000 is often blocked on Windows)."""

from app import create_app

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5001, debug=True)
