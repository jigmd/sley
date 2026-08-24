from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent.parent
ENTRY = ROOT / "typescript" / "tests" / "browser.entry.ts"
TSUP = ROOT / "typescript" / "node_modules" / ".bin" / "tsup"
EXPECTED = {
    "outputs": [2, 4],
    "processType": "undefined",
    "projectedValue": 7,
    "status": "completed",
    "terminalCount": 2,
    "total": 6,
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sley-browser-") as directory:
        output = Path(directory)
        subprocess.run(
            [
                str(TSUP),
                "--no-config",
                str(ENTRY),
                "--format",
                "iife",
                "--platform",
                "browser",
                "--target",
                "es2022",
                "--out-dir",
                str(output),
                "--minify",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        bundles = list(output.glob("*.js"))
        if len(bundles) != 1:
            raise AssertionError(f"expected one browser bundle, found {bundles!r}")
        bundle = bundles[0]
        source = bundle.read_text(encoding="utf-8")
        if "node:" in source:
            raise AssertionError("browser bundle contains a Node.js built-in import")

        with sync_playwright() as playwright:
            executable_path = os.environ.get("SLEY_BROWSER_EXECUTABLE")
            browser = playwright.chromium.launch(
                executable_path=executable_path,
                headless=True,
            )
            try:
                page = browser.new_page()
                page.add_script_tag(path=str(bundle))
                page.wait_for_function(
                    "globalThis.__sleyBrowserResult !== undefined || "
                    "globalThis.__sleyBrowserError !== undefined",
                    timeout=10_000,
                )
                error = page.evaluate("globalThis.__sleyBrowserError")
                if error is not None:
                    raise AssertionError(f"browser runtime failed: {error}")
                observed = page.evaluate("globalThis.__sleyBrowserResult")
            finally:
                browser.close()

    if observed != EXPECTED:
        raise AssertionError(
            "browser snapshot mismatch\n"
            f"expected={json.dumps(EXPECTED, sort_keys=True)}\n"
            f"actual={json.dumps(observed, sort_keys=True)}"
        )
    print("Browser runtime: Chromium bundle snapshot agrees")


if __name__ == "__main__":
    main()
