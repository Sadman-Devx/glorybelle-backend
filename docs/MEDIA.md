# Admin media storage

Admin uploads use a dedicated S3-compatible bucket. Existing customer-facing
uploads continue to use the project's default Cloudinary/local storage.

## Configuration

Set these variables on the Django server; never expose the access key or secret
in the frontend:

- `ADMIN_MEDIA_S3_BUCKET`: private bucket for staging uploads and processed files.
- `ADMIN_MEDIA_S3_REGION`: bucket region (defaults to `eu-central-1`).
- `ADMIN_MEDIA_S3_ENDPOINT_URL`: optional provider endpoint; leave empty for AWS S3.
- `ADMIN_MEDIA_S3_ACCESS_KEY_ID` and `ADMIN_MEDIA_S3_SECRET_ACCESS_KEY`: optional
  when the server uses an attached IAM role. Set both or neither.
- `ADMIN_MEDIA_PUBLIC_BASE_URL`: CDN base URL used by product and admin responses,
  for example `https://media.example.com`.
- `ADMIN_MEDIA_PRESIGN_TTL`: presigned upload lifetime in seconds (60–900; defaults
  to 300).

Keep the bucket private. Give the Django role permission to `PutObject`,
`GetObject`, `HeadObject`, and `DeleteObject` for the bucket's `staging/` and
`catalog/` prefixes. Configure the CDN with read-only origin access to `catalog/`;
do not grant public bucket listing or direct public writes. Configure a bucket
CORS rule permitting `PUT` from the exact admin frontend origin with the
`Content-Type` request header. A lifecycle rule should expire unregistered
objects under `staging/` after one day.

## Upload flow

1. Authenticated Manager/Superuser sends
   `POST /api/admin/media/presign/` with
   `{"content_type":"image/jpeg","size_bytes":12345}`. The only accepted types
   are JPEG, PNG, and WebP; the declared size must be 1 byte to 10 MiB.
2. The response includes `upload_id`, a short-lived `upload_url`, method `PUT`,
   and the exact `Content-Type` header. The declared content length is bound into
   the signature; the browser uploads the bytes directly to that URL.
3. Send `POST /api/admin/media/` with `{"upload_id":123,"alt_text":"..."}`.
   Django checks the object size again, decodes it and checks the actual image
   format, rejects animated or oversized-dimension images, strips source
   metadata by re-encoding, creates 400/800/1600-pixel WebP renditions, and
   removes the staging object.

Only the manager who requested the presigned URL can register that upload.
Unregistered staging keys are not returned as public URLs.

## API

- `GET /api/admin/media/`: paginated library; supports `search`, `usage_count`,
  `ordering`, `page`, and `page_size`.
- `DELETE /api/admin/media/{id}/`: removes an asset only when it is not linked to
  a product; linked assets return `409 Conflict`.
- `GET /api/admin/products/` and `/api/admin/products/{id}/`: paginated,
  searchable/filterable catalogue management.
- `POST /api/admin/products/` and `PUT`, `PATCH`, `DELETE` on a product detail
  path manage products. Slugs are generated when omitted. A product referenced
  by an order is deactivated, never deleted.
- `/api/admin/products/{id}/variants/` and its `/{variant_id}/` detail path
  manage variants. `reserved_quantity` is read-only and stock cannot be lowered
  below the reserved quantity. An ordered variant is deactivated on delete.
- `GET` or `PUT /api/admin/products/{id}/images/` reads/replaces the ordered
  gallery. The PUT body is
  `{"media_ids":[1,2],"primary_media_id":1}`; each media ID must be unique and
  the primary ID must be in the gallery (or null for an empty gallery).

All catalogue endpoints require the admin JWT. Viewer can list/read products,
variants, and media; Manager and Superuser can write. Product, variant, and
product-image changes are captured by simple-history with the request user.
