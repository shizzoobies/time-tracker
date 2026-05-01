import sys
import os

# Run from the app directory without a terminal window (pythonw.exe handles .pyw files)
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
os.chdir(_dir)

from main import TimeTrackerApp

app = TimeTrackerApp()
app.mainloop()
