# Site content and staff administration

## Managed content

Run `python manage.py migrate` to install the `site_content` tables. Content images
reference the protected admin media library; an image in use by a product, hero,
Instagram grid, or testimonial cannot be deleted from the library.

Public, read-only endpoints:

- `GET /api/site-content/hero/` — active hero images in configured order; paginated.
- `GET /api/site-content/instagram/` — the Instagram link and seven ordered images.
  Until all seven distinct images are configured, this returns an empty grid so the
  storefront keeps its existing static images.
- `GET /api/site-content/testimonials/` — active testimonials; paginated.

Manager-protected endpoints under `/api/admin/content/` manage the hero list, the
Instagram singleton, and testimonials. Viewers can read them but cannot modify them.
Hero and testimonial list endpoints support pagination, search, filters, and ordering.
The admin UI is at `/admin/contenuti`.

## Staff accounts

All `/api/admin/staff/` endpoints require a superuser, enforced by the API:

- `GET /api/admin/staff/` — paginated, searchable staff list; filter with
  `is_active=true|false`.
- `POST /api/admin/staff/` — invite with `email`, optional `first_name` and
  `last_name`, and `role` (`manager` or `viewer`). The account is created with an
  unusable password and receives an email link to set one.
- `PATCH /api/admin/staff/<id>/` — assign a manager or viewer role.
- `POST /api/admin/staff/<id>/deactivate/` — deactivate a non-superuser account.
- `POST /api/admin/staff/<id>/password-link/` — email a password setup/reset link.
- `GET /api/admin/staff/role-audit/` — paginated and searchable role-change history.

Role history includes invitations and changes made through the Django admin user
form. Password hashes and password fields are never included in the staff API
responses. The existing Django admin remains available to superusers.

Password links use the configured `FRONTEND_URL`, `DEFAULT_FROM_EMAIL`, and Django
email backend, and finish at `/reset-password`. Keep the admin media storage
configuration and `ADMIN_SESSION_SECRET` server-side.

## Verification checklist

- A manager can edit content; a viewer can read but every write is denied.
- A customer and anonymous caller cannot access admin content or staff endpoints.
- A superuser can invite staff, set roles, deactivate non-superusers, and resend a
  password link; every role assignment is auditable.
- Staff invitations contain a working one-time password link; API responses contain
  no password or hash.
- With no active managed content, the homepage displays the existing hero,
  Instagram images, and testimonials.
- Content-backed media cannot be deleted until its references are removed.
