"""
Test of the database tools — without the LLM, calls the functions directly.

Run (the database in Docker must be running):
    python tests/test_db_tools.py
"""

import json
import os
import sys
from datetime import date, timedelta

# Add the project root's src/ folder to the import path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from db.hotel_tools import (
    get_hotel_info, get_room_types, check_availability, find_guest,
    get_guest_reservations, create_reservation, cancel_reservation,
    list_services, list_campaigns, execute_tool,
)


def show(title, result):
    print(f"\n{'='*60}\n{title}\n{'='*60}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


t = date.today()
ci = (t + timedelta(days=10)).isoformat()
co = (t + timedelta(days=13)).isoformat()

show("1. Otel məlumatı", get_hotel_info())
show("2. Otaq tipləri", get_room_types())
show(f"3. Boş otaqlar ({ci} → {co})", check_availability(ci, co))
show("4. Qonaq axtarışı (seed-dəki Rəşad)", find_guest("+994501234567"))
show("5. Qonağın rezervasiyaları", get_guest_reservations("+994501234567"))
show("6. Xidmətlər", list_services())
show("7. Kampaniyalar", list_campaigns())

show("8. Yeni rezervasiya (test qonağı)",
     create_reservation("+994559998877", "Test Qonaq", "Stəndard", ci, co))

show("9. Həmin rezervasiyanın yoxlanışı", get_guest_reservations("+994559998877"))

show("10. Ləğv", cancel_reservation("+994559998877", ci))

show("11. Dispatcher testi (LLM-in çağırdığı yol)",
     execute_tool("check_availability", {"check_in": "sabah", "check_out": ci}))

show("12. Xəta halı (səhv tarix)",
     execute_tool("check_availability", {"check_in": "dünən yox e", "check_out": co}))

print("\n✅ Bütün testlər icra olundu. Yuxarıdakı nəticələri yoxlayın.")
