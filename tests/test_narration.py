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

    def test_every_utterance_is_a_button_or_an_auto_read(self):
        """Narration is invoked from exactly two places, and no third.

        Buttons, or the two auto-read effects. This used to assert that every
        `narrate.` line sat inside a `SpeakButton`, which stopped being true
        when auto-read landed - so it now checks the real rule: anything that
        is not a button must be inside an effect guarded by `acted.current`.
        """
        cases = read(os.path.join(FRONTEND, "screens", "Cases.tsx"))

        # All auto-reading funnels through one guarded helper, so there is a
        # single place the gate can be checked - and a single place to lose it.
        helper = re.search(r"const autoSay = useCallback\((.*?)\n  \}, \[",
                           cases, re.S)
        self.assertIsNotNone(helper, "the guarded autoSay helper is missing")
        body = helper.group(1)
        self.assertIn("acted.current", body,
                      "autoSay is not gated on a real interaction, so it can "
                      "fire on arrival")
        self.assertIn("autoRead", body, "autoSay ignores the setting")

        # Effects may call autoSay; nothing else may reach the narrator.
        # Checked per *statement*, not per line: these calls wrap, and a
        # line-based check reported a false positive on the continuation.
        flat = re.sub(r"\s+", " ", cases)
        for match in re.finditer(r"narrate\.\w+\(", flat):
            before = flat[max(0, match.start() - 160):match.start()]
            self.assertTrue(
                "SpeakButton" in before or "autoSay(" in before,
                "narration reached a third place, near: %s"
                % flat[match.start():match.start() + 60])
        # The gate lives in autoSay, so the screen must not reach past it to
        # the handle. (autoSay's own `say(text)` is the one legitimate call.)
        self.assertEqual(
            len(re.findall(r"narration\.say\(", cases)), 0,
            "the screen calls narration.say() directly, bypassing autoSay's gate")
        self.assertEqual(
            len(re.findall(r"\bsay\(text\)", cases)), 1,
            "expected exactly one raw say(), inside autoSay")

    def test_auto_read_cannot_loop_on_its_own_renders(self):
        """The bug this test exists for, because it is silent when it happens.

        `useNarration` returns a fresh handle object every render. An effect
        that depends on the handle therefore re-runs on every render - and
        `say()` flips `speaking` and notifies subscribers, which *causes* a
        render. That is a loop with no brake, and the screen looks perfect
        while it runs: the right text, the right order, 24,664 utterances for
        one decision. It was found by counting calls, not by watching.

        So: no `useEffect` in the case screen may depend on the bare handle.
        """
        cases = read(os.path.join(FRONTEND, "screens", "Cases.tsx"))
        deps = re.findall(r"\}, \[([^\]]*)\]\)", cases)
        for group in deps:
            names = [d.strip() for d in group.split(",") if d.strip()]
            self.assertNotIn(
                "narration", names,
                "an effect depends on the whole narration handle, which is a "
                "new object every render: [%s]" % group.strip())

    def test_a_passage_is_never_read_twice(self):
        """Belt and braces on top of the deps, since the failure is silent."""
        cases = read(os.path.join(FRONTEND, "screens", "Cases.tsx"))
        self.assertIn("spokenFor", cases,
                      "no guard against re-reading the same passage")
        self.assertRegex(cases, r"if \(spokenFor\.current === mark\) return")

    def test_arriving_at_a_case_is_silent(self):
        """`acted` starts false and is set only by choosing or continuing."""
        cases = read(os.path.join(FRONTEND, "screens", "Cases.tsx"))
        self.assertIn("const acted = useRef(false)", cases)
        sets = re.findall(r"acted\.current = true", cases)
        self.assertEqual(len(sets), 2,
                         "expected exactly two arming points (choose and "
                         "advance); found %d" % len(sets))

    def test_narration_and_auto_read_are_both_off_by_default(self):
        body = read(SPEECH)
        match = re.search(r"export const DEFAULTS: NarrationSettings = \{(.*?)\}",
                          body, re.S)
        self.assertIsNotNone(match, "DEFAULTS is missing")
        block = match.group(1)
        self.assertRegex(block, r"enabled:\s*false", "narration defaults to on")
        self.assertRegex(block, r"autoRead:\s*false", "auto-read defaults to on")


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
