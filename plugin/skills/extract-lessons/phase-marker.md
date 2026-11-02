# Phase marker and mutex

## Step 1: mutex check, phase kind

For a `phase` kind opportunity, also check `.compass/tmp/phase-reports/<phase-id>/.processed`: its presence is the same backstop collision this check has always guarded against, from the legacy path where the phase-report directory carried its own mutex before opportunities existed.

## Step 8: mutex marker

Write `.compass/tmp/phase-reports/<phase-id>/.processed` (empty file) so the backstop path skips this phase.

For a `signal` or `interval` kind opportunity, there is no phase-report directory to mark; step 9's `compass capture-close` call is what closes the opportunity and stops a later pass from picking it up again.
