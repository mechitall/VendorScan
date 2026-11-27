# VendorScan × Norma

How our team of two (GitHub accounts `mechitall` and `edrethardo`), working with coding
agents, used Norma on this repository.

## Submission note (paste into the form)

> **Finding we accepted:** rule `py-maint-no-print-1.0`, "print() in production code"
> (Medium, Maintainability), in `vendorscan/idealo_auth.py` line 105 (`_open_browser`).
> During the one-time idealo sign-in the user must see the sign-in URL in the terminal if no
> browser opens. An INFO log is not shown unless logging is configured, so the user could
> wait for a sign-in link they never see. The line runs only during sign-in, not while
> handling a scan result, and the reason is written next to it.
>
> **Consistency between authors:** the first idealo client (PR #2) printed its output with
> `print()`, and Norma's scan of `main` lists three Medium findings of this rule in that
> version of `idealo_client.py`. The same pattern came back in later code by another author,
> and Norma reported it on PR #6. Those calls were replaced; the one exception above stays.
> Our shared rules (no committed keys, `Decimal` for money, `httpx` instead of `requests`)
> are written down for every agent. Our Norma policy did not return any rules through Norma
> MCP when we last checked, so we do not claim that Norma enforced them.

## Workspace and policy

- **Workspace:** _<workspace name as shown in Norma>_ (fill in before submitting)
- **Intended policy rules:**
  1. No hardcoded API keys, tokens or secrets in any file. Keys live in a
     git-ignored `.env`; idealo OAuth tokens in a git-ignored `.idealo_oauth.json`.
  2. Money uses `decimal.Decimal`, never `float`, in `vendorscan/`.
  3. Ban the `requests` package; use `httpx` (already used by the MCP SDK).
- **Status:** the "Policies" ruleset for this repository returned **0 rules** through Norma
  MCP on 27 November (last checked shortly after 18:28 CET). Create the policy under
  **New policy** (Describe, Review, **Apply**), for example:
  `Ban the requests package in every repository. Use httpx instead. Severity: High.`
  Only after `get_rules_for_ruleset` returns it, update the submission note above.
- The open issues Norma MCP lists for `main` (three `print()` calls, `idealo_client.py`
  lines 80, 88 and 91) come from an older scan; those calls are no longer in the file.
  Run a new scan in Norma before submitting so the project score reflects the current code.

## Found and fixed

| PR | First check | Fix | Re-check |
|---|---|---|---|
| #3 cost engine | 13 × Medium "Legacy typing generics" (`Optional[X]` in `models.py`) | Built-in `X \| None` | ✅ No issues |
| #6 extension | 18 issues: 3 × Medium `print()` in production code, 1 × Medium long timeout also applies to the connection, magic-number timeouts (Low) | Named timeouts with a separate connect timeout in `vendorscan/settings.py`; logging instead of `print()` | 8 left |
| #6 (second round) | 7 × Low `open()` without explicit encoding | `encoding="utf-8"` on every file read/write | 1 left: the accepted `print()` |

## PR #7: deliberate demonstration (second GitHub author: `edrethardo`, with Claude Code)

The violation in `norma_demo.py` was planted **on purpose** (PLAN.md section 15, step 4)
to show a finding being caught and fixed. It is not an organic finding. Nothing imports the file.

| Commit | What it contains | Norma PR check |
|---|---|---|
| `9d57a39` | `requests` and float money in `docs/test_norma.py` | No issues reported |
| `d8b4d20` | Same rules broken in `norma_demo.py`, plus `print()` and an unnamed timeout | 2 issues: Medium `print()` in production code (line 18), Low magic-number timeout (line 14) |
| `1b9d71f` | Fixed in place: logging, named timeouts, `httpx`, `Decimal` | No issues |

The fix was also checked with Norma `live_check` (clean) before the commit, and recorded with
`register_applied_actions`. The earlier commits on this PR were **not** checked through MCP
first, because Norma was not yet connected for this author.

**Open: the team policy is not taking effect.** On 27 November the "Policies" ruleset for this
repository returned **0 rules** through Norma MCP, and neither `requests` nor float money was
reported. Until that is fixed in the Norma workspace, do not claim that Norma enforces the three
policy rules listed above, including in the submission note.

## Pull requests

Norma GitHub App comments, as checked on 27 November:

| PR | Author | Norma comment |
|---|---|---|
| #1, #3, #6 | `mechitall` | yes, merged |
| #7, #8 | `edrethardo` (with Claude Code) | yes, merged |
| #2 | `edrethardo` | none |
| #4, #5 | `mechitall` | none |

## Norma in the agent loop

`AGENTS.md` instructs every coding agent to run a Norma check on the files it changed before
each commit, and to fix findings or explain in the PR why one stays. The Norma MCP server is
set up in `.mcp.json` (Claude Code) and `.codex/config.toml` (Codex). This was not followed
for every commit: for example, PR #8 relied on the pull request check, as its description
says. On PR #7 the fix was checked with `live_check` before the commit.
