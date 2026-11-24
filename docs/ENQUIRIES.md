# Richieste di contatto e Atelier

## API pubblica

`POST /api/enquiries/` accepts `name`, `email`, `topic`, and `message`.
`topic` must be `prodotto`, `ordine`, `atelier`, or `altro`; the optional
`atelier_type` is `anelli`, `collane`, or `orecchini` and is valid only for
the `atelier` topic. Messages are limited to 5,000 characters, and HTML tags
are removed before persistence. Include the hidden `website` honeypot field in
the form; a non-empty value receives the same generic success response without
creating a record or sending email. Requests are limited to five per IP per
hour.

Successful requests are persisted before an Italian text and HTML notification
is sent to `ENQUIRY_NOTIFICATION_EMAIL`. Its default is
`DEFAULT_FROM_EMAIL` (`ordini@glorybelle.it`); production should set the
recipient to the shop's monitored inbox. The notification uses Django's
configured email backend and sets the customer's address as `Reply-To`.
Production SMTP settings can be supplied through `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `EMAIL_USE_TLS` / `EMAIL_USE_SSL`.

## Admin API

All endpoints below use the dedicated admin authentication and server-side
role permissions:

| Method and path | Access | Behavior |
|---|---|---|
| `GET /api/admin/enquiries/` | Manager, Viewer, superuser | Paginated list; filter by `status`, `topic`, `atelier_type`, `assigned_to`, `created_after`, or `created_before`; search name, email, and message; supports ordering. |
| `GET /api/admin/enquiries/assignees/` | Manager, Viewer, superuser | Paginated, searchable active staff Managers and superusers for assignment controls. |
| `GET /api/admin/enquiries/{id}/` | Manager, Viewer, superuser | Detail including the customer message and internal notes. |
| `PATCH /api/admin/enquiries/{id}/` | Manager, superuser | Update `status` (`new`, `in_progress`, `answered`, `closed`) and/or `assigned_to`. Assignment is limited to active staff Managers and superusers. Set status to `answered` when a response has been sent. |
| `POST /api/admin/enquiries/{id}/notes/` | Manager, superuser | Add an internal note with its author and timestamp. |

Viewers can read enquiries but cannot change status, assignment, or notes.
Customer-facing APIs never include internal notes. The built-in Django admin
also exposes enquiries to superusers; enquiry deletion is disabled there.
Replies are sent through the shop's mail client; after sending, mark the
enquiry `answered` with the PATCH endpoint.
