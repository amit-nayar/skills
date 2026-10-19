#!/bin/bash
# Stop and delete the per-session emulators agents boot with the monorepo's
# android/tools/testUtils/emulator.sh, once the session that started them is clearly gone.
#
# emulator.sh names each AVD after its port (pixel_2-5556, pixel_2-5558, ...) and launches it
# headless, so there is no window to close. An agent that crashes or runs out of turns before its
# `emulator.sh delete --port <port>` leaves a qemu process holding 2-5 GB of RAM, and an AVD of a
# few GB on disk, until something kills it.
#
# Two passes:
#   1. Running emulators whose AVD matches ^<device>-<port>$ and that have been up longer than
#      CLEANUP_EMULATOR_MAX_AGE_HOURS: `adb emu kill`, then SIGKILL if still alive.
#   2. AVDs matching that name: deleted when pass 1 stopped their emulator, or when no emulator
#      is running and they have been untouched for an hour. The hour covers the gap between
#      emulator.sh creating an AVD and launching it.
#
# Hand-made AVDs (Pixel_2, Pixel_Fold, 4gb, ...) never match the name pattern and are never touched.
#
# Usage: cleanup-agent-emulators.sh [--live]
#   (no args)  dry-run: prints what WOULD be stopped/deleted
#   --live     actually stops and deletes them
#
# Env: CLEANUP_EMULATOR_MAX_AGE_HOURS  uptime after which a running emulator counts as left
#                                      behind (default 6)
#      CLEANUP_EMULATOR_DEVICE         emulator.sh's device profile, the AVD name prefix
#                                      (default pixel_2)
#      ANDROID_AVD_HOME                AVD directory (default ~/.android/avd)
#
# Output: one line per action, machine-parseable:
#   EMULATOR_STOPPED|<avd>|<uptime_hours>
#   AVD_DELETED|<avd>
#   SKIPPED_EMULATOR_YOUNG|<avd>|<uptime_hours>

LIVE=false
[[ "${1:-}" == "--live" ]] && LIVE=true

readonly MAX_AGE_HOURS="${CLEANUP_EMULATOR_MAX_AGE_HOURS:-6}"
readonly DEVICE="${CLEANUP_EMULATOR_DEVICE:-pixel_2}"
readonly AVD_HOME="${ANDROID_AVD_HOME:-$HOME/.android/avd}"
readonly SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export PATH="$SDK/platform-tools:$SDK/emulator:$SDK/cmdline-tools/latest/bin:$PATH"

# ps etime is [[dd-]hh:]mm:ss; prints whole seconds.
etimeToSeconds() {
    local etime="$1" days=0 h=0 m=0 s=0
    if [[ "$etime" == *-* ]]; then days="${etime%%-*}"; etime="${etime#*-}"; fi
    IFS=: read -r -a parts <<< "$etime"
    case ${#parts[@]} in
        3) h=${parts[0]}; m=${parts[1]}; s=${parts[2]} ;;
        2) m=${parts[0]}; s=${parts[1]} ;;
        1) s=${parts[0]} ;;
    esac
    echo $(( 10#$days * 86400 + 10#$h * 3600 + 10#$m * 60 + 10#$s ))
}

# Space-padded AVD name lists (macOS /bin/bash is 3.2: no associative arrays).
running=" "
stopped=" "

# Pass 1. The launcher execs qemu with the same arguments, so the qemu process carries
# `-avd <name>`; emulator.sh puts the port in the name.
while read -r pid etime exe args; do
    # Match on the executable, not anywhere in the command line: a shell or editor whose arguments
    # merely mention `qemu-system ... -avd pixel_2-5556` must never be killed.
    [[ "$(basename "$exe")" == qemu-system* ]] || continue
    [[ " $args" =~ -avd[[:space:]]+(${DEVICE}-([0-9]+))([[:space:]]|$) ]] || continue
    avd="${BASH_REMATCH[1]}"
    port="${BASH_REMATCH[2]}"
    [[ "$running" == *" $avd "* ]] && continue
    running="$running$avd "
    ageSeconds=$(etimeToSeconds "$etime")
    ageHours=$(( ageSeconds / 3600 ))
    if (( ageSeconds < MAX_AGE_HOURS * 3600 )); then
        echo "SKIPPED_EMULATOR_YOUNG|$avd|$ageHours"
        continue
    fi
    echo "EMULATOR_STOPPED|$avd|$ageHours"
    stopped="$stopped$avd "
    $LIVE || continue
    # Backgrounded rather than wrapped in `timeout`, which launchd's PATH may not have: a wedged
    # emulator can leave the console command hanging, and the SIGKILL below ends it either way.
    adb -s "emulator-$port" emu kill > /dev/null 2>&1 &
    adbPid=$!
    for _ in 1 2 3 4 5 6 7 8; do kill -0 "$pid" 2>/dev/null || break; sleep 2; done
    kill -9 "$pid" 2>/dev/null
    kill "$adbPid" 2>/dev/null
done < <(ps -axo pid=,etime=,command= | grep '[q]emu-system')

# Pass 2.
shopt -s nullglob
for ini in "$AVD_HOME/$DEVICE"-*.ini; do
    avd="$(basename "$ini" .ini)"
    [[ "$avd" =~ ^${DEVICE}-[0-9]+$ ]] || continue
    dir="$AVD_HOME/$avd.avd"
    if [[ "$stopped" != *" $avd "* ]]; then
        [[ "$running" == *" $avd "* ]] && continue
        # Recently created or used: a session may be about to launch it.
        [[ -n "$(find "$ini" "$dir" -maxdepth 0 -mmin -60 2>/dev/null)" ]] && continue
    fi
    echo "AVD_DELETED|$avd"
    $LIVE || continue
    # avdmanager also drops the AVD from its own records; the rm covers an AVD it can't parse, or
    # an SDK without cmdline-tools.
    avdmanager delete avd -n "$avd" > /dev/null 2>&1
    rm -rf "$dir" "$ini"
done
