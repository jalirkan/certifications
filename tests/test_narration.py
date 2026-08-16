"""Structural guards on case narration.

Narration is a browser feature and there is no JS test runner in this project,
so these are source-level checks in the same idiom as
`test_casesession.py::test_runner_source_is_cp1252_safe`. They are weaker than
running the code and stronger than nothing, and they guard the two rules that
would be invisible if broken:

* **Options are never spoken.** The narrative suits audio; the four options are
  a comparison task, and reading them aloud converts a reading task into a
  working-memory one. The real guarantee is the type system - `speak()` takes a
  branded `Narratable` that only the `narrate` allow-list can mint - so these
  tests check that the mechanism is still in place rather than re-checking
  every call site.
* **Local voices only.** A cloud voice would ship case text to a vendor and
  break the offline promise invisibly, which is the worst way for it to break.

    python tests/test_narration.py
"""

from __future__ import annotations

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FRONTEND = os.path.join(ROOT, "frontend", "src")
SPEECH = os.path.join(FRONTEND, "lib", "speech.ts")

# Fields that are prose, consumed in order, and suit audio.
NARRATABLE_FIELDS = ("opening", "situation", "consequence", "narrative", "prompt")


def source_files():
    for root, _, names in os.walk(FRONTEND):
        for name in names:
            if name.endswith((".ts", ".tsx")):
                yield os.path.join(root, name)


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class TestTheFeatureExists(unittest.TestCase):
    def test_the_speech_module_is_on_disk(self):
        self.assertTrue(os.path.isfile(SPEECH), "frontend/src/lib/speech.ts is missing")

    def test_the_case_screen_uses_it(self):
        cases = read(os.path.join(FRONTEND, "screens", "Cases.tsx"))
        self.assertIn("useNarration", cases)
        self.assertIn("SpeakButton", cases)


class TestOptionsAreNeverSpoken(unittest.TestCase):
    """The design call this feature turns on."""

    def test_only_the_speech_module_touches_the_synthesiser(self):
        """One door, so the guarantee is checkable rather than a promise."""
        offenders = []
        for path in source_files():
            if os.path.abspath(path) == os.path.abspath(SPEECH):
                continue
            body = read(path)
            if "speechSynthesis" in body or "SpeechSynthesisUtterance" in body:
                offenders.append(os.path.relpath(path, ROOT))
        self.assertEqual(offenders, [],
                         "speech synthesis reached outside lib/speech.ts: %s"
                         % offenders)

    def test_speak_refuses_a_bare_string(self):
        """`speak(text: Narratable)`, not `speak(text: string)`.

        This is what makes passing `option.text` a compile error rather than a
        code-review catch.
        """
        body = read(SPEECH)
        self.assertRegex(body, r"speak\s*\(\s*text\s*:\s*Narratable\s*\)",
                         "speak() no longer requires a branded Narratable")
        self.assertRegex(body, r"export type Narratable\b",
                         "the Narratable brand is gone")

    def test_only_the_allow_list_can_mint_narratable_text(self):
        """`narratable()` is the single cast, and it is not exported."""
        body = read(SPEECH)
        casts = re.findall(r"as Narratable\b", body)
        self.assertEqual(len(casts), 1,
                         "found %d casts to Narratable; there must be exactly one, "
                         "inside narratable()" % len(casts))
        self.assertNotRegex(body, r"export\s+function\s+narratable\b",
                            "narratable() is exported, so anything can be spoken")

    def test_the_allow_list_covers_prose_and_nothing_else(self):
        body = read(SPEECH)
        match = re.search(r"export const narrate = \{(.*?)\n\} as const",
                          body, re.S)
        self.assertIsNotNone(match, "the narrate allow-list is missing")
        block = match.group(1)

        # Every entry reads one named prose field.
        fields = set(re.findall(r"=>\s*narratable\(\w+\.(\w+)\)", block))
        self.assertTrue(fields, "no allow-list entries found")
        for field in fields:
            self.assertIn(field, NARRATABLE_FIELDS,
                          "'%s' is not prose and must not be narratable" % field)

        for banned in ("options", "option", "text", "key"):
            self.assertNotIn(banned, fields,
                             "the allow-list can reach option text via '%s'" % banned)

    def test_no_call_site_narrates_an_option(self):
        pattern = re.compile(
            r"narrate\.\w+\(\s*[\w.]*\b(option|options|opt|o)\b", re.I)
        for path in source_files():
            body = read(path)
            hit = pattern.search(body)
            self.assertIsNone(
                hit, "%s narrates an option: %r"
                % (os.path.relpath(path, ROOT), hit.group(0) if hit else ""))


class TestLocalVoicesOnly(unittest.TestCase):
    """A cloud voice would break the offline promise, and do it silently."""

    def test_the_voice_list_filters_on_localservice(self):
        body = read(SPEECH)
        self.assertRegex(body, r"localService\s*===\s*true",
                         "voices are not filtered to local ones, or the filter "
                         "is loose enough to admit an undefined flag")

    def test_there_is_no_fallback_when_no_local_voice_exists(self):
        """Refusing to speak is the safe failure; speaking to a vendor is not."""
        body = read(SPEECH)
        self.assertIn("unavailableReason", body)
        self.assertNotIn("localService === false", body)
        self.assertNotIn("localService !== true", body)

    def test_the_reason_is_shown_rather_than_the_feature_hidden(self):
        ui = read(os.path.join(FRONTEND, "ui", "Narration.tsx"))
        self.assertIn("unavailableReason", read(SPEECH))
        self.assertIn("n.reason", ui)


class TestNoAutoplayAndNoOverlap(unittest.TestCase):
    def test_speech_stops_on_unmount_and_on_node_change(self):
        ui = read(os.path.join(FRONTEND, "ui", "Narration.tsx"))
        self.assertIn("narrator.stop()", ui)
        self.assertRegex(ui, r"useEffect\(\(\) => \{\s*narrator\.stop\(\)",
                         "no effect stops speech when the node changes")

    def test_nothing_speaks_without_a_press(self):
        """Every call into the narrator hangs off a handler, never an effect."""
        cases = read(os.path.join(FRONTEND, "screens", "Cases.tsx"))
        for line in cases.splitlines():
            if "narrate." in line:
                self.assertIn("SpeakButton", line,
                              "narration is invoked outside a button: %s" % line.strip())

    def test_narration_is_off_until_switched_on(self):
        body = read(SPEECH)
        self.assertRegex(body, r"DEFAULTS[^=]*=\s*\{\s*enabled:\s*false",
                         "narration defaults to on")


class TestSettingsPersist(unittest.TestCase):
    def test_voice_rate_and_enabled_are_stored(self):
        body = read(SPEECH)
        self.assertIn("localStorage.setItem", body)
        self.assertIn("localStorage.getItem", body)
        for field in ("enabled", "voice", "rate"):
            self.assertIn(field, body)

    def test_unreadable_storage_does_not_break_the_screen(self):
        """Private browsing throws on setItem; narration must still work."""
        body = read(SPEECH)
        self.assertRegex(body, r"try \{\s*localStorage\.setItem")


class TestTheCliAsymmetryIsDocumented(unittest.TestCase):
    """Every other feature works from both front ends. This one cannot, and
    §6 of the brief says that must be written down rather than discovered."""

    def test_the_readme_says_narration_is_browser_only(self):
        readme = read(os.path.join(ROOT, "README.md")).lower()
        self.assertIn("narrat", readme,
                      "the README does not mention narration at all")
        self.assertTrue(
            any(word in readme for word in ("browser only", "browser-only",
                                            "not available in the cli",
                                            "no terminal equivalent")),
            "the README does not state that narration is browser-only")


if __name__ == "__main__":
    unittest.main(verbosity=2)
