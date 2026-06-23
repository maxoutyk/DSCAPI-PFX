# Team members — customer guide

IG E-Sign lets organization **owners** invite **team members** who can sign PDFs in the portal and via USB under the same billing account and quota pool.

## Who is affected

- **Existing customers:** Nothing changes until you invite someone. Every account registered before teams stays an **owner** with full access.
- **API integrations:** Unchanged. Use the same `dsc_live_…` API keys; signing and GST calls remain organization-scoped.
- **Pro / Pro+ quota:** Shared across owner and members — one pool per organization.

## Roles

| Capability | Owner | Member |
|------------|:-----:|:------:|
| Dashboard & recent activity | ✓ | ✓ |
| Portal sign & USB sign | ✓ | ✓ |
| View signature styles | ✓ | ✓ (read-only) |
| API docs & agent download | ✓ | ✓ |
| Usage report & CSV/PDF export | ✓ | — |
| API keys & saved certificates | ✓ | — |
| Company profile & GST portal | ✓ | — |
| Pair / revoke USB agent | ✓ | — |
| Invite & remove members | ✓ | — |

Members do **not** receive their own API keys in v3. Integrations (ERP, scripts) should continue using keys created by the owner.

## Inviting a member

1. Sign in as the organization owner.
2. Open **Team** (`/dashboard/team/`).
3. Enter the teammate’s email and send the invite.
4. They receive a link valid for **72 hours** (configurable via `TEAM_INVITE_HOURS`).

The invitee can sign in with an existing account or create a password **without** registering a new organization.

## Removing a member

Owners can remove members from the Team page. The user account remains; only access to your organization is removed.

If a removed person knew an API key string, that key still works until the owner revokes it — treat keys as secrets and rotate when offboarding integrators.

## Environment flag

Team invites are gated by:

```env
TEAMS_ENABLED=true   # default false until you enable on your server
TEAM_INVITE_HOURS=72
```

With `TEAMS_ENABLED=false`, the Team page lists members but email invites are disabled.

## Support scenarios

| Situation | Action |
|-----------|--------|
| Invite expired | Owner resends from Team → Pending invites |
| Wrong email invited | Owner revokes pending invite and sends a new one |
| User already owns another org | They must use a different email or contact support |
| Ownership transfer | Not self-serve in v3.0 — contact support |

## Related documentation

- Implementation spec: [2026-06-21-team-members-v3.md](./superpowers/specs/2026-06-21-team-members-v3.md)
- API note: portal **Team members** section in dashboard API docs PDF
