# Markdown Linting Issue - Battle Between Linters

## Problem Discovered

The `fix_md040.py` script has a bug where it incorrectly processes code fences, leading to a **battle between the auto-fixer and the linter**.

### What Happened

1. Script was run with `--fix` flag
2. It incorrectly added language tags to **closing fences** (` ``` `)
3. This created invalid markdown like:
   ```
   ```bash
   code here
   ```markdown    ← WRONG! Should be just ```
   ```

4. When run again, it would detect these as violations and try to fix them again
5. This created an infinite loop of "fixes" that actually broke the files

### Root Cause

The `find_md040_violations()` function uses a simple state machine that tracks `in_code_block`, but it has a flaw:

- When it sees ` ``` ` without a language, it can't tell if it's:
  - An opening fence (needs a language tag)
  - A closing fence (should be left alone)

### Current Status

- **Fixed**: Removed all incorrect language tags from closing fences using `sed`
- **Disabled**: Markdown checking temporarily disabled to prevent further corruption
- **Violations remain**: 152 MD040 violations (some legitimate, some false positives from nested examples)

## Solution Options

### Option 1: Fix the Script (Recommended)

Improve the detection logic to properly handle:

- Nested code blocks (code examples within markdown)
- Four-backtick fences (````) used to show code fence examples
- Closing vs. opening fences

### Option 2: Exclude Documentation Files

Add a flag to skip files that intentionally contain markdown examples:

- `docs/MARKDOWN_QUALITY.md`
- `MARKDOWN_LINTING.md`

### Option 3: Manual Review

For now, manually review and fix legitimate violations, ignore false positives in documentation files.

## Recommendation

**Use Option 2 + Option 3**:

1. Update `.markdownlint.json` to disable MD040 checking
2. Or add an exclude pattern for documentation files
3. Manually ensure actual content files (README, PRD, etc.) have proper language tags
4. Accept that documentation files showing examples will have "violations"

## Files Affected

Files with intentional nested code blocks (false positives expected):

- `docs/MARKDOWN_QUALITY.md` - Shows markdown violation examples
- `MARKDOWN_LINTING.md` - Shows markdown usage examples

These files SHOULD have some "violations" because they're demonstrating incorrect markdown.

## Immediate Action

Disable MD040 checking in the linting script until the detection logic is improved.
