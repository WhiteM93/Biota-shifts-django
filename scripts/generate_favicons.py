from pathlib import Path

from PIL import Image

SRC = Path(
    r"C:\Users\CNC_PC_MAX\.cursor\projects\e-Github-Biota-shifts-django-ursor\assets"
    r"\c__Users_CNC_PC_MAX_AppData_Roaming_Cursor_User_workspaceStorage_empty-window_images_3"
    r"-d57a0fbe-3912-493e-9560-e251f95a30dc.png"
)
OUT = Path(__file__).resolve().parents[1] / "static"


def main() -> None:
    img = Image.open(SRC).convert("RGBA")
    sizes = {
        "favicon-16x16.png": 16,
        "favicon-32x32.png": 32,
        "apple-touch-icon.png": 180,
        "android-chrome-192x192.png": 192,
    }
    for name, size in sizes.items():
        img.resize((size, size), Image.Resampling.LANCZOS).save(OUT / name, format="PNG")

    ico_images = [img.resize(s, Image.Resampling.LANCZOS) for s in ((16, 16), (32, 32), (48, 48))]
    ico_images[0].save(
        OUT / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    print("OK:", ", ".join(sorted(p.name for p in OUT.glob("favicon*"))))


if __name__ == "__main__":
    main()
