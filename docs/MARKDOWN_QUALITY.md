# Markdown Quality Assurance

This document explains the markdown linting system and how to prevent common markdown violations.

## Overview

We enforce three critical markdown rules to maintain documentation quality:

- **MD032**: Lists must be surrounded by blank lines
- **MD026**: No trailing punctuation in headings
- **MD040**: Code blocks must have language specifiers

## Prevention Strategy

### 1. Automated Scripts

Three Python scripts automatically detect and fix violations:

- `fix_md032.py` - List formatting
- `fix_md026.py` - Heading punctuation
- `fix_md040.py` - Code block languages

**Usage:**

```bash
# Check for violations
python fix_md032.py
python fix_md026.py
python fix_md040.py

# Auto-fix violations
python fix_md032.py --fix
python fix_md026.py --fix
python fix_md040.py --fix

# Verbose output
python fix_md032.py --verbose
```

### 2. Pre-Commit Hook

A Git pre-commit hook automatically checks markdown files before commits.

**Location:** `.git/hooks/pre-commit`

**How it works:**

1. Detects markdown files in the commit
2. Runs all three linting scripts
3. Blocks the commit if violations are found
4. Provides fix commands

**To bypass (not recommended):**

```bash
git commit --no-verify
```

### 3. Make Commands

Convenient commands for markdown quality:

```bash
# Check markdown files
make markdown-check

# Auto-fix all violations
make markdown-fix

# Run all checks (code + markdown)
make all
```

### 4. Linting Script

A unified linting script checks all rules at once.

**Location:** `scripts/lint-markdown.sh`

**Usage:**

```bash
./scripts/lint-markdown.sh
```

## Common Violations and Fixes

### MD032: Lists Without Blank Lines

**Violation:**

```
Some text here

- List item 1
- List item 2

More text
```

**Fixed:**

```
Some text here

- List item 1
- List item 2

More text
```

### MD026: Trailing Punctuation in Headings

**Violation:**

```
## Configuration
### Important Note
```

**Fixed:**

```
## Configuration
### Important Note
```

### MD040: Code Blocks Without Language

**Violation:**

````
```
def example():
    pass
```
````

**Fixed:**

````
```
def example():
    pass
```
````

## Language Auto-Detection (MD040)

The `fix_md040.py` script automatically detects code languages:

- **Python**: `def`, `import`, `class`, `print()`
- **Bash**: `#!/bin/bash`, `echo`, `cd`, `ls`
- **JavaScript**: `function`, `const`, `let`, `=>`
- **JSON**: `{"key": "value"}`
- **YAML**: `key: value`
- **SQL**: `SELECT`, `INSERT`, `UPDATE`
- **HTML**: `<tag>`, `</tag>`
- **CSS**: `selector { property: value; }`
- **Markdown**: `# `, `## `, `- []`

Defaults to `text` if language cannot be detected.

## Integration with Development Workflow

### Before Committing

Run quality checks:

```bash
make all
```

This runs:

1. Python linting (black, ruff)
2. All tests
3. Markdown linting

### When Writing Markdown

Follow these guidelines:

1. **Lists**: Always add blank lines before and after lists
2. **Headings**: Never end headings with punctuation (`:`, `!`, `.`, etc.)
3. **Code Blocks**: Always specify the language

**Good:**

````
## Installation

To install dependencies:

```bash
pip install -r requirements.txt
```

The following packages are required:

- numpy
- pandas
- requests

Configuration is stored in YAML format.
````

**Bad:**

````
## Installation
To install dependencies:
```
pip install -r requirements.txt
```
The following packages are required:

- numpy
- pandas
- requests

Configuration is stored in YAML format.
````

### IDE Integration

#### VSCode

Install the [markdownlint extension](https://marketplace.visualstudio.com/items?itemName=DavidAnson.vscode-markdownlint):

```bash
code --install-extension DavidAnson.vscode-markdownlint
```

Configuration is already set in `.markdownlint.json`.

#### PyCharm/IntelliJ

Enable markdown linting in:

**Settings → Languages & Frameworks → Markdown → Linting**

## Configuration

### .markdownlint.json

The project includes a `.markdownlint.json` configuration file:

```json
{
  "default": true,
  "MD013": false,
  "MD033": false,
  "MD041": false,
  "MD032": true,
  "MD026": true,
  "MD040": true,
  "line-length": false
}
```

**Enabled rules:**

- MD032: Lists need blank lines
- MD026: No trailing punctuation
- MD040: Code blocks need language

**Disabled rules:**

- MD013: Line length (too restrictive)
- MD033: HTML allowed (for flexibility)
- MD041: First line doesn't need to be H1

## Troubleshooting

### Pre-commit hook not running

Check that the hook is executable:

```bash
chmod +x .git/hooks/pre-commit
```

### False positives in MD040

Some code blocks within markdown examples may show as violations. These can be ignored if the outer block has a language specifier.

### Scripts not found

Ensure you're running from the project root:

```bash
cd /path/to/ev-charging-optimizer
./scripts/lint-markdown.sh
```

## Benefits

### Consistency

All markdown files follow the same standards, making documentation easier to read and maintain.

### Readability

Proper list spacing and code highlighting improve documentation clarity.

### Automation

Violations are caught automatically before they reach the repository.

### IDE Support

VSCode and other editors provide real-time feedback with the markdownlint extension.

## Maintenance

### Adding New Rules

To add a new markdown rule:

1. Create a new Python script `fix_mdXXX.py`
2. Add it to `scripts/lint-markdown.sh`
3. Update this documentation
4. Update `.markdownlint.json`

### Disabling Rules

To disable a rule temporarily:

1. Edit `.markdownlint.json`
2. Set the rule to `false`
3. Document why in this file

## Statistics

As of initial implementation:

- **379 violations fixed** across 15 files
- **MD032**: 197 violations
- **MD026**: 53 violations
- **MD040**: 129 violations

All violations have been resolved. The prevention system ensures no new violations are introduced.

## Quick Reference

```bash
# Check markdown quality
make markdown-check

# Fix all violations
make markdown-fix

# Run all quality checks
make all

# Individual rule checks
python fix_md032.py --verbose
python fix_md026.py --verbose
python fix_md040.py --verbose

# Individual rule fixes
python fix_md032.py --fix
python fix_md026.py --fix
python fix_md040.py --fix