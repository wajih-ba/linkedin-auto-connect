# Git Push Rejected Fix Page

This project is a single-page troubleshooting website that explains how to fix:

`! [rejected] main -> main (fetch first)`

## What is included

- `index.html`: A complete Tailwind-based page with copyable Git commands.
- Safe fix flow using `git pull --rebase origin main`.
- Conflict resolution notes.
- Optional force-push warning section.

## How to use

1. Open `index.html` in your browser.
2. Copy the suggested command sequence.
3. Run commands inside your local repository terminal.

Recommended sequence:

```bash
git fetch origin
git pull --rebase origin main
git push -u origin main
```

If conflicts happen:

```bash
git add .
git rebase --continue
git push -u origin main
```

If your local and remote histories are unrelated:

```bash
git pull origin main --allow-unrelated-histories
git push -u origin main
```

## Notes

- Use `git push --force-with-lease origin main` only if you intentionally want to overwrite remote history.
- The page is static and requires no build step.
