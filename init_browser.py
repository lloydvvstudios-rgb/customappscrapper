import os
import subprocess
import sys

def install_browser():
    print("Checking for Playwright browsers...")
    # Set the path to be strictly inside the app folder
    cache_dir = os.path.join(os.getcwd(), '.cache')
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = cache_dir

    try:
        # Run the installation directly via subprocess
        print("Installing Chromium...")
        subprocess.check_call([sys.executable, '-m', 'playwright', 'install', 'chromium'])
        subprocess.check_call([sys.executable, '-m', 'playwright', 'install-deps', 'chromium'])
        print(f"Browser installed successfully to {cache_dir}")
    except Exception as e:
        print(f"Failed to install browser: {e}")
        sys.exit(1)

if __name__ == "__main__":
    install_browser()
