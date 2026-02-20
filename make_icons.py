from PIL import Image
from pathlib import Path

SOURCE_PNG = Path("assets/funnelforge.png")

DESKTOP_ICON = Path("funnelforge_desktop.ico")
TASKBAR_ICON = Path("funnelforge_taskbar.ico")

img = Image.open(SOURCE_PNG).convert("RGBA")

# Desktop icon (Explorer/shortcuts)
img.save(DESKTOP_ICON, sizes=[(256, 256)])

# Taskbar/titlebar icon
img.save(TASKBAR_ICON, sizes=[(32, 32)])

print("Icons created successfully:")
print(" -", DESKTOP_ICON)
print(" -", TASKBAR_ICON)
