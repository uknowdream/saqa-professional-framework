# Accessibility manual verification plan

This plan supplements the automated axe-core checks. It is a test protocol, not evidence that the target has passed. Mark any unexecuted item `UNVERIFIED`; never infer conformance from a clean automated scan.

## Execution controls

- Record target URL/build, commit SHA, browser and version, OS, viewport, assistive technology and version, tester, date, and evidence links.
- Use only an authorized test environment and non-production data.
- Run each scenario on a representative critical user journey and record the exact page/state.
- For every defect, capture reproduction steps, expected/actual behavior, severity, owner, and retest result.
- Status values: `PASS`, `FAIL`, `BLOCKED`, `UNVERIFIED`. A blocked or unrun scenario is not a pass.

## Keyboard-only test matrix

| ID | Procedure | Expected result | WCAG 2.2 mapping |
| --- | --- | --- | --- |
| KBD-01 | Reload the page, keep hands off the mouse, press Tab through the interface. | Focus moves to each operable control in a meaningful sequence; no unexpected focus loss. | 2.1.1, 2.4.3 |
| KBD-02 | Use Shift+Tab to reverse through the same controls. | Reverse navigation is possible and predictable. | 2.1.1, 2.4.3 |
| KBD-03 | Observe every focused element at desktop and mobile viewport sizes. | Focus indicator is visible and not fully obscured by sticky headers, dialogs, or overlays. | 2.4.7, 2.4.11 |
| KBD-04 | Operate links, buttons, menus, checkboxes, radio groups, and dialogs with keyboard only. | Enter/Space and arrow-key behavior follows the control's semantics; no mouse-only action is required. | 2.1.1, 4.1.2 |
| KBD-05 | Open any modal/dialog, navigate inside, close with supported keyboard controls, and continue. | Focus is managed inside the dialog, Escape works when expected, and focus returns to the invoking control. | 2.1.1, 2.4.3 |
| KBD-06 | Try to move focus outside any modal that must be modal. | Keyboard focus does not escape into background content while the modal is active. | 2.1.2 |
| KBD-07 | Follow the primary flow (search/browse/select) using only keyboard. | Every step can be completed, with no keyboard trap. | 2.1.1, 2.1.2 |
| KBD-08 | Zoom to 200% and reflow to a narrow viewport; repeat the primary flow. | Controls and focus remain visible/usable; no essential content is lost. | 1.4.10, 2.4.11 |

## Screen-reader test matrix

| ID | Platform / AT | Procedure | Expected result | WCAG 2.2 mapping |
| --- | --- | --- | --- | --- |
| SR-01 | Windows + NVDA + Firefox or Chrome | Navigate headings, landmarks, and regions. | Page structure and meaningful headings are announced in a logical hierarchy. | 1.3.1, 2.4.6 |
| SR-02 | Windows + NVDA | Navigate interactive controls and form fields. | Controls expose a meaningful accessible name, role, state, and value. | 4.1.2, 3.3.2 |
| SR-03 | iOS + VoiceOver + Safari | Complete the main browse/search flow. | Reading order is logical and controls are discoverable and operable. | 1.3.2, 2.1.1 |
| SR-04 | Android + TalkBack + Chrome | Complete the main browse/search flow at mobile viewport. | Touch exploration and swipe navigation expose the same essential actions and information. | 1.3.2, 2.1.1 |
| SR-05 | Any supported AT | Trigger validation and status changes. | Errors, loading state, and important result updates are communicated without requiring visual-only cues. | 4.1.3, 3.3.1 |
| SR-06 | Any supported AT | Inspect images, icon-only buttons, and links. | Informative images have appropriate alternatives; interactive controls have specific names. | 1.1.1, 2.4.4, 4.1.2 |

## Evidence record template

For each test ID, record:

- **Status:** PASS / FAIL / BLOCKED / UNVERIFIED
- **Target/build/commit:**
- **Browser, OS, assistive technology and versions:**
- **Steps and page/state:**
- **Expected / actual result:**
- **Evidence URL or artifact path:**
- **Defect ID / owner / severity:**
- **Retest date and result:**

## Exit criteria

- All critical keyboard-only flows have a recorded result.
- No unresolved critical keyboard trap or blocker remains.
- Screen-reader results are recorded for the platforms in the product's support policy.
- Automated axe findings and manual findings are triaged separately.
- Any untested WCAG criterion remains explicitly `UNVERIFIED`; this plan alone does not establish WCAG conformance.
