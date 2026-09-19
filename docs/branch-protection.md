# Branch protection checklist (run after GitHub remote exists)

1. Settings → Branches → Add rule for `main`
2. Require a pull request before merging
3. Require status checks to pass: `python`, `web`
4. Require branches to be up to date before merging (optional)
5. Do not allow force pushes
6. Do not allow deletions

Also create `develop` and open PRs into it for ongoing work.
