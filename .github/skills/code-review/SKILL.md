---
description: Use when reviewing code changes, pull requests, diffs, or recently edited files for bugs, risks, style issues, missing tests, and maintainability problems.
---

# Code Review

Review the code like a practical senior engineer.

## Goals

Find issues that matter:

- correctness bugs
- edge cases
- security risks
- performance problems
- broken assumptions
- confusing code
- missing or weak tests
- unnecessary complexity
- inconsistent style with the existing project

## Process

1. First understand the user’s review target:
   - current git diff
   - specific files
   - recent changes
   - pull request
   - feature implementation

2. Inspect only the relevant files first.
   Do not scan the whole repository unless necessary.

3. Prioritize high-impact findings.
   Do not nitpick formatting unless it affects readability or consistency.

4. For each issue, explain:
   - what is wrong
   - why it matters
   - where it appears
   - how to fix it

5. Do not edit files unless the user explicitly asks.

## Output format

Use this structure:

### Summary

Briefly describe the overall quality and main risk.

### Findings

List issues in priority order.

For each finding:

- Severity: Critical / High / Medium / Low
- Location: file and function/section if known
- Issue:
- Why it matters:
- Suggested fix:

### Tests to add or run

Suggest targeted tests only.

### Final recommendation

Say whether the change is safe to merge, needs small fixes, or needs major revision.

## Rules

- Be direct but not harsh.
- Do not invent problems.
- If something is uncertain, say what needs to be checked.
- Prefer small fixes over large rewrites.
- Do not suggest new dependencies unless clearly justified.
- Do not review unrelated files.
