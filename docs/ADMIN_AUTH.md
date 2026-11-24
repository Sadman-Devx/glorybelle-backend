# Admin API authentication

The admin API is mounted at `/api/admin/`. Password authentication alone does
not issue tokens: `POST /login/` returns a short-lived MFA challenge, and
`POST /mfa/verify/` issues tokens only after a TOTP or one-time recovery code
is accepted. On first login, the challenge starts enrollment; the TOTP secret
is returned once and must be confirmed before a session is created. Recovery
codes are returned once at enrollment and are stored only as keyed hashes.

The policy applies to staff assigned to the `Manager` or `Viewer` group and
superusers. The Django admin fallback uses `django-otp` and only authorizes a
verified OTP session. A staff account must complete MFA enrollment through
the admin API before using that fallback.

Admin access tokens expire after 10 minutes. Refresh tokens rotate and are
blacklisted after rotation. Each token is bound to a database-backed admin
session; requests refresh its activity timestamp and are rejected after 30
minutes idle. Password changes, role changes, account deactivation, logout,
and logout-everywhere revoke the corresponding sessions. Three failed
password or MFA attempts lock the account for 15 minutes and trigger an email
alert to active superusers.

The recommended deployment is the frontend BFF described in
`ADMIN_SPEC.md`: keep both tokens server-side and expose only a secure,
HttpOnly frontend session cookie to the browser. Do not put Django admin tokens
in customer local storage.

`GET /api/admin/me/` returns the user identity, role, and role permissions.
`POST /api/admin/logout/` revokes the current admin session;
`POST /api/admin/logout-everywhere/` revokes all active admin sessions for the
current user. `GET /api/admin/audit/` is superuser-only and requires
`model=order`, `model=product`, or `model=productvariant`; `object_id` is
optional. Results are paginated by 25 (maximum 100), searchable, and
orderable. The audit list contains history metadata and changed field names,
not historical field values.

Order, product, and product-variant snapshots are recorded by
django-simple-history. The history request middleware records the actor for
authenticated Django admin and API requests. Changes made outside a request,
such as background jobs, should set `_history_user` explicitly when an actor
is available.

## CORS deployment configuration

`CORS_ALLOWED_ORIGINS` is an exact comma-separated origin allowlist.
Wildcards are rejected and `CORS_ALLOW_ALL_ORIGINS` is disabled. Local settings
explicitly allow the two local Next.js development origins. The repository
does not identify the deployed frontend hostname; production deployments must
set `CORS_ALLOWED_ORIGINS` to their actual frontend origins rather than
reusing local development values. The BFF's server-to-server requests do not
rely on browser CORS.
