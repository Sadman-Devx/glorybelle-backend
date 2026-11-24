# GLORYBELLE Admin Launch Security Checklist

## Production environment

Set these on the backend, not in browser-exposed `NEXT_PUBLIC_*` variables:

- `SECRET_KEY`: unique, random Django key; never use the example value.
- `DEBUG=False` and `ALLOWED_HOSTS` restricted to the production API hosts.
- `DATABASE_URL`: production PostgreSQL connection.
- `REDIS_URL`: shared Redis cache for cross-worker login throttling and lockout.
- `CORS_ALLOWED_ORIGINS`: exact HTTPS storefront/admin origins only.
- `FRONTEND_URL`: canonical HTTPS frontend URL used in staff password setup links.
- `ADMIN_SESSION_IDLE_TIMEOUT_SECONDS=1800`.
- `ADMIN_LOGIN_FAILURE_LIMIT=3` and `ADMIN_LOGIN_LOCKOUT_SECONDS=900`.
- `ADMIN_MFA_CHALLENGE_TTL_SECONDS=600` and
  `ADMIN_MFA_RECOVERY_CODE_COUNT=10`.
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` or `EMAIL_USE_SSL`, and
  `DEFAULT_FROM_EMAIL`. Active superusers must have deliverable email addresses
  to receive lockout alerts.

The Next.js server also needs `ADMIN_SESSION_SECRET`, a random 32-byte
hexadecimal value. It seals the admin access/refresh tokens in the
`gb_admin_session` cookie. Keep it server-only and distinct from Django's
`SECRET_KEY`. The cookie is `HttpOnly`, `Secure` in production, `SameSite=Lax`,
scoped to `/api/admin`, and slides with authenticated activity up to the
30-minute idle policy.

Stripe credentials stay on the backend. End-to-end refund tests must use an
isolated backend configured with a Stripe **test-mode** secret key (`sk_test_`)
and test orders only; never run refund tests against live credentials.

## Authentication and session checks

- [ ] Apply migrations, including `django_otp` and `admin_api` migrations.
- [ ] Confirm every staff account has a unique, confirmed TOTP device.
- [ ] Enroll new staff through `/admin/login`; verify no access/refresh token or
  admin cookie is issued before a valid TOTP confirmation.
- [ ] Store the one-time recovery codes in the approved password manager; test
  one code, then confirm that it cannot be reused.
- [ ] Verify login accepts TOTP, rejects invalid/expired/replayed MFA challenges,
  rate-limits attempts, and emails active superusers after the third failure.
- [ ] Verify 30 minutes idle expires the session; an active request slides the
  idle window; logout-everywhere, password change, role change, and deactivation
  revoke old sessions.
- [ ] Verify the Django admin fallback rejects password-only sessions and works
  only after OTP verification. Keep Django admin enabled for superusers.
- [ ] Confirm no admin credentials, TOTP secrets, recovery codes, or tokens are
  written to browser local storage, frontend bundles, logs, or analytics.

## Authorization and response protections

- [ ] Run the resolver-driven `/api/admin/` route matrix. Anonymous requests must
  receive `401`, customer tokens and wrong roles `403`, and permitted staff
  roles must pass authorization.
- [ ] Confirm superuser-only staff and role-audit endpoints reject Manager and
  Viewer accounts.
- [ ] Verify `/api/admin/` and `/admin/` responses include a CSP with
  `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, and
  `X-Frame-Options: DENY`.
- [ ] Inspect the production `gb_admin_session` cookie for `HttpOnly`,
  `Secure`, `SameSite=Lax`, path `/api/admin`, and the 30-minute maximum age.
- [ ] Confirm admin pages use `noindex`, are absent from sitemap output, and are
  not allowed by robots rules.

## Validation and release

- [ ] Run backend tests, including the route matrix, MFA enrollment/recovery,
  lockout, idle expiry, session revocation, headers, and audit tests.
- [ ] Run frontend `npx tsc --noEmit`, `npx eslint src`, and `npm run build`.
- [ ] Run Playwright login/MFA, order status, Stripe test-mode cancellation and
  refund, image upload, and role-restriction flows in the isolated test setup.
- [ ] Run `python manage.py check --deploy` with production settings and the
  production environment. Resolve all warnings before release.
- [ ] Verify backups and an approved rollback procedure before applying
  production migrations.
