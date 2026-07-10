---
name: verify-android-change
description: Verify an Android SDK change end-to-end on an emulator before declaring it done — build, install the catalog, drive the affected screen, capture screenshots and logcat evidence. Use after any nontrivial change to android/ SDK or viewer code, before handing work back or committing.
allowed-tools: Bash, Glob, Grep, Read
argument-hint: what changed and (optionally) which catalog example exercises it
---

# Verifying an Android SDK change

Never report an Android change as complete based on a successful edit or compile alone.
Verify it the way Amit would on a device, and hand back evidence, not intent.

The `./tools/android` command layer lives outside the monorepo. Use the absolute path:

```bash
ANDROID_TOOL=~/dev/me/android-adb-skill/tools/android
```

Prefer `--json` output and reason from it. Fall back to raw `adb` only when the command
layer can't do something.

## 0. Decide if this is emulator-verifiable

Some changes need real hardware and must be handed to Amit instead:

- Physical input hardware (mouse wheel, stylus, external keyboard) — emulators don't forward these reliably.
- Real memory pressure / LMK behavior, thermal, or performance characteristics.
- Anything Amit tests with his heavy CAD document on the Galaxy Tab S9.

For these: **stop after building and installing.** Hand back exact manual steps (screen to open,
gestures to perform, expected result) plus the one-shot logcat command to capture evidence
(`adb logcat -d`, not streaming — wireless adb is flaky). Everything else, continue below.

## 1. Scope the change

Read the diff (`git diff` / `git diff master...`) and identify the user-visible surface.
Pick the catalog example or screen that exercises it (search `android/examples/catalog/` for
a matching `SdkExample`). If nothing in the catalog exercises the change, say so explicitly
rather than verifying an adjacent screen and calling it covered.

Note: Amit often keeps a deliberately-uncommitted `SdkExample.kt` in the catalog — never
revert, stage, or overwrite it.

## 2. Get a device

```bash
$ANDROID_TOOL device list --json
```

- Multiple devices attached and none specified → stop and ask which one.
- A physical device attached → prefer the emulator for automated verification; don't drive
  Amit's hardware unless asked.
- None → `$ANDROID_TOOL device avds --json`, then `device start-emulator --avd-name <name> --json`
  and wait for boot.

## 3. Pre-flight: check animation settings BEFORE trusting your eyes

```bash
adb shell settings get global animator_duration_scale
```

If `0`, animated UI (indeterminate `LinearProgressIndicator`, transitions) draws **nothing**
even when the code is correct. Do not conclude a view is missing or broken with animations
disabled — temporarily restore with
`adb shell settings put global animator_duration_scale 1`, verify, then set it back to the
original value.

## 4. Build and install

From `android/` in the monorepo checkout you're working in:

```bash
./gradlew :examples:catalog:installDebug        # catalog (com.pspdfkit.catalog)
./gradlew :examples:compose-catalog:installDebug  # compose catalog, if the change is Compose-side
./gradlew :viewer:installDebug                  # viewer app changes
```

A green build is a prerequisite, not a result.

## 5. Drive the change and collect evidence

1. `$ANDROID_TOOL debug clear-logs --json`
2. `$ANDROID_TOOL app launch --package com.pspdfkit.catalog --json`
3. Screenshot the starting state: `$ANDROID_TOOL screenshot --out /tmp/verify-<change>-before.png --json`
4. Navigate to the affected screen with `ui find`, `input tap-element`, `wait element`,
   `scroll find`. Verify after every interaction with `ui dump` or a screenshot — never
   chain blind taps.
5. Exercise the change directly: for a new control, tap it and confirm the state change;
   for rendering changes, open a document that hits the code path; for behavior changes,
   perform the triggering gesture.
6. Screenshot the result: `/tmp/verify-<change>-after.png`, plus checkpoints at each
   meaningful state.

## 6. Check the logs

```bash
$ANDROID_TOOL debug logs --package com.pspdfkit.catalog --level W --lines 300 --json
```

- Zero new errors; explain any new warnings.
- Look specifically at PSPDFKit/Nutrient tags for the touched subsystem.
- Obfuscated stack trace → use the /retrace skill with the build's mapping file.

## 7. Report

Report pass/fail with concrete evidence: screenshots (read them back and describe what they
show), relevant log lines, and the exact commands run. If any step fails, fix the issue and
rerun from step 4 — do not hand back partially verified work. If verification is impossible
(hardware-only, no exercising example), state exactly what was and wasn't verified and give
Amit the manual steps for the rest.
