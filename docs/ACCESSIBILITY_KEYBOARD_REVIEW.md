# Accessibility keyboard review protocol

## Automated keyboard-focus diagnostic

The Juice Shop accessibility gate records a 12-step Tab traversal sample in the evidence field `details.keyboard_focus_diagnostic`. It captures the focused element, role, accessible-name candidate, tabindex, and rendered visibility when available.

This is **diagnostic evidence only**. It does not certify keyboard accessibility, prove that focus indicators are visible, or verify that every workflow can be completed without a pointer. It is not currently a mandatory release-certification domain.

## Manual review checklist

Run these checks against the authorized local reference target and representative application workflows. Record browser/version, target build, reviewer, date, result, and evidence.

- [ ] Complete the primary navigation and one end-to-end user flow using only Tab, Shift+Tab, Enter, Space, and arrow keys where expected.
- [ ] Confirm focus moves in a logical order and never becomes trapped unexpectedly.
- [ ] Confirm every focused interactive element has a clearly visible focus indicator at normal and high-contrast settings where supported.
- [ ] Confirm menus, dialogs, and overlays open and close with expected keyboard controls; focus enters and returns appropriately.
- [ ] Confirm disabled controls cannot be activated and their disabled state is communicated.
- [ ] Confirm form errors are announced or discoverable and focus can reach the relevant error and field.
- [ ] Confirm skip navigation or equivalent efficient access to main content when appropriate.
- [ ] Repeat representative tasks with a screen reader supported by the test environment.

## Evidence and interpretation

Store the automated diagnostic in the existing accessibility evidence artifact. Record manual checklist results separately and link them to the same commit/build where possible. Mark untested scenarios `UNVERIFIED`; do not infer WCAG conformance from a passing axe scan or a sampled focus sequence.

A release certification claim requires the relevant mandatory domain to be explicitly configured in the certification gate and to have fresh passing evidence. This checklist alone does not change the gate.
