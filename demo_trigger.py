"""
demo_trigger.py  –  Fire a simulated alert for demos/testing.

Usage:
  python demo_trigger.py          # create trigger (fires alert in ~30s)
  python demo_trigger.py --clear  # remove trigger (simulates fix → verifier passes)

How it works:
  AegisNode's Observer checks for 'trigger_alert.txt'.
  If it exists, error rate returns 15% → alert fires.
  Delete the file to simulate the fix working.
"""

import sys
import os

TRIGGER_FILE = "trigger_alert.txt"

if "--clear" in sys.argv:
    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)
        print("✅ trigger_alert.txt removed — simulating fix success.")
        print("   The Verifier will now see 0% error rate and mark fix as PASSED.")
    else:
        print("Nothing to clear.")
else:
    with open(TRIGGER_FILE, "w") as f:
        f.write("DEMO ALERT TRIGGERED\n")
    print("🔴 trigger_alert.txt created!")
    print("   AegisNode will detect this in the next poll cycle (~30s).")
    print("   Watch the terminal running 'python main.py'.")
    print()
    print("   To simulate the fix working:")
    print("   python demo_trigger.py --clear")
