# VendorScan × Norma

How our team (one human with Claude Code, one with Codex) kept agent-written
code consistent with Norma.

## Submission note (paste into the form)

> **Finding we accepted:** `print()` in production code (Maintainability), in
> `vendorscan/idealo_auth.py` (`_open_browser`). During the one-time idealo
> OAuth sign-in, the user must see the sign-in URL in the terminal when no
> browser opens. Logging hides INFO by default, so switching would make sign-in
> silently hang for anyone without a desktop browser. It runs once per machine,
> never in the request path, and the reason is written next to the line.
>
> **How the policy kept authors consistent:** our policy bans hardcoded keys,
> floats for money and the `requests` package, and `AGENTS.md` makes both agents
> (Claude Code and Codex) run a Norma check before committing. Example of one
> agent repeating another's mistake: the first idealo client (Codex, PR #2)
> printed its output with `print()`, and Norma's scan of `main` flagged it as
> Maintainability issues. Claude later wrote new modules and repeated the same
> pattern; Norma flagged `print()` again on PR #6. We fixed it for both authors
> (logging, explicit stdout for CLI output) and kept one deliberate exception,
> documented above. Norma also caught both agents hardcoding their own timeouts
> (20, 30, 60 s); they now share named timeouts in `vendorscan/settings.py`.
>
> _TODO before submitting: confirm in Norma (Issues tab of the `main` scan) that
> the 3 Medium Maintainability issues are the `print()` calls in `idealo_client.py`._

## Workspace and policy

- **Workspace:** _<team name>_ (fill in)
- **Policy rules** (created in the Norma workspace):
  1. No hardcoded API keys, tokens or secrets in any file. Keys live in a
     git-ignored `.env`; idealo OAuth tokens in a git-ignored `.idealo_oauth.json`.
  2. Money uses `decimal.Decimal`, never `float`, in `vendorscan/`.
  3. Ban the `requests` package; use `httpx` (already used by the MCP SDK).

## Found and fixed

| PR | First check | Fix | Re-check |
|---|---|---|---|
| #3 cost engine | 13 × Medium "Legacy typing generics" (`Optional[X]` in `models.py`) | Built-in `X \| None` | ✅ No issues |
| #6 extension | 18 issues: 3 × Medium `print()` in production code, 1 × Medium long timeout also applies to the connection, magic-number timeouts (Low) | Named timeouts with a separate connect timeout in `vendorscan/settings.py`; logging instead of `print()` | 8 left |
| #6 (second round) | 7 × Low `open()` without explicit encoding | `encoding="utf-8"` on every file read/write | 1 left: the accepted `print()` |

## Pull requests

All changes went through pull requests, each checked by the Norma GitHub App
before merging. Authors: `mechitall` (Claude Code) and `edrethardo` (Codex).

## Norma in the agent loop

`AGENTS.md` instructs every coding agent to run a Norma check on the files it
changed before each commit and to either fix findings or explain in the PR why
one stays. The Norma MCP server is configured for both agents:
`.mcp.json` (Claude Code) and `.codex/config.toml` (Codex).
