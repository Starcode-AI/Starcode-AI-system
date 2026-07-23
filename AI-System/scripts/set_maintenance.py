import argparse
import json

from app.db import SessionLocal, init_db
from app.models import SystemSetting


def main() -> None:
    parser = argparse.ArgumentParser(description="Enable or disable maintenance mode")
    parser.add_argument("state", choices=["on", "off"])
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        item = db.get(SystemSetting, "maintenance_mode") or SystemSetting(key="maintenance_mode")
        item.value_json = json.dumps(args.state == "on")
        db.add(item)
        db.commit()
    print(f"Maintenance mode: {args.state}")


if __name__ == "__main__":
    main()
