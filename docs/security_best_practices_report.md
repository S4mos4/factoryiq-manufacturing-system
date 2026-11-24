# FactoryIQ security review

The local demo uses PostgreSQL constraints, fixed SQL plus bound inputs, explicit server-side authorization, and a separate server flag that blocks writes in the public demo configuration. Runtime logs hide SQLAlchemy bound values. The browser keeps the operator token in page memory and serves API calls from the same origin. Input schemas reject unexpected fields, and request and CSV limits cover streamed bodies. React escapes record text and CSV exports neutralize formula prefixes. Published API docs can be disabled and deployment hosts allowlisted.

## Findings

1. **Medium. Shared operator identity.** The single demo operator token authorizes all writes and identifies one database actor in the audit trail. It cannot distinguish individual operators. Keep the write mode private. A multi-user installation would need individual accounts, revocation, and authorization policy.
2. **Medium. Public traffic and data growth.** There is no application-level rate limit, and list/report reads are designed around a bounded demo dataset. Public hosting should use edge limits and an isolated synthetic database. Sustained operational loads require server-side pagination and capacity testing.
3. **Low. Chart styling policy.** The frontend CSP allows inline styles for Recharts, while script execution is restricted to the same origin. A stricter style policy would need a different chart styling strategy.
4. **Low. Audit integrity boundary.** Application writes record actor and event in the same transaction. A PostgreSQL owner can still amend historic rows. A compliance deployment would need a restricted database writer and protected audit export.

## Verification

Sixteen PostgreSQL-backed Pytest checks and six Chromium workflow checks passed. Dependency scans reported zero known vulnerabilities for the pinned Python and npm dependencies at the time of review. The repository was reviewed for configuration secrets, upstream academic content, and personal data before private delivery. This review covers the application and dependency configuration, with further deployment infrastructure and load testing pending.
