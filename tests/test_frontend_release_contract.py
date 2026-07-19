from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class FrontendReleaseContractTests(unittest.TestCase):
    def test_auth_success_uses_safe_skill_return_or_3d_scene(self) -> None:
        source = (REPO_ROOT / "frontend/src/auth/AuthPages.tsx").read_text(
            encoding="utf-8"
        )
        authorize_source = (REPO_ROOT / "app/static/skill-authorize.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('window.location.href = "/"', source)
        self.assertNotIn("window.location.href = '/'", source)
        self.assertEqual(source.count('nav("/scene", { replace: true })'), 1)
        self.assertIn('candidate.startsWith("/skill/authorize?")', source)
        self.assertIn("window.location.replace(next)", source)
        self.assertIn(
            "location.replace('/3d/login?next=' + encodeURIComponent(next))",
            authorize_source,
        )

    def test_legacy_public_pages_do_not_reintroduce_html_sinks_or_demo_passwords(
        self,
    ) -> None:
        page_paths = (
            "app/static/welcome.html",
            "app/static/services.html",
            "app/static/economy.html",
            "app/static/index.html",
        )
        forbidden_patterns = (
            r"\binnerHTML\b",
            r"\bouterHTML\b",
            r"\binsertAdjacentHTML\b",
            r"\bdocument\.write\b",
            r"\bquickFill\b",
            r"\badmin123\b",
        )

        for relative_path in page_paths:
            source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                with self.subTest(path=relative_path, pattern=pattern):
                    self.assertIsNone(re.search(pattern, source))

    def test_built_3d_entry_uses_the_stable_release_asset(self) -> None:
        index_source = (REPO_ROOT / "app/static/3d/index.html").read_text(
            encoding="utf-8"
        )
        asset_path = REPO_ROOT / "app/static/3d/assets/app.js"

        self.assertIn('src="/3d/assets/app.js"', index_source)
        self.assertTrue(asset_path.is_file())
        self.assertGreater(asset_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
