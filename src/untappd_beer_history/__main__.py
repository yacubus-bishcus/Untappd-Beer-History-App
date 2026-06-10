import ctypes
import sys
import traceback


if __name__ == "__main__":
    try:
        from untappd_beer_history.app import main

        main().main_loop()
    except Exception:
        details = traceback.format_exc()
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                None,
                details,
                "Untappd Beer History - Startup Error",
                0x10,
            )
        else:
            raise
