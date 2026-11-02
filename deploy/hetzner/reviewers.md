# Anonymous reviewers with an invitation code

Additional, optional access on `https://review.prodigi-marburg.de`. The existing
Cloudflare mail-code access on `alita.prodigi-marburg.de` stays unchanged.
No Caddy, additional identity provider or user database required.

## Permissions and limits

- No e-mail, no name: every reviewer receives a random invitation code (192 bits).
- Read all documents/metadata and download originals; both chats with **their own OpenRouter key**.
- No uploads, metadata changes, rebuilds or admin rights – not even with forged e-mail headers.
- Codes are valid for 30 days by default; sessions for at most eight hours and never longer than the code.
- The server stores only code hashes and expiry dates; the session cookie is host-bound, Secure,
  HttpOnly and SameSite=Strict. Keys and chats stay, as before, only in the page storage.
- Anyone who holds a valid code can use/pass it on. One code per reviewer allows
  separate revocation but proves no identity. Do not share codes publicly or in URL parameters.
- Cloudflare may process IP addresses and connection data. This is no guarantee of complete
  network anonymity. Downloads cannot be recalled afterwards.

## 1. Provide the code and enable the backend first

On the VM in the current checkout `/opt/alita/app`, **before** the reviewer route is published:

```bash
umask 077
python3 tools/reviewer_invites.py --origin https://review.prodigi-marburg.de --days 30
```

The command updates `.env` atomically, creates the session key if needed and shows the invitation code
**once**. The output is confidential; pass it privately to the editorial office. Note the Invitation ID
and expiry date that are also shown, for later revocation. Do not commit real codes/secrets.
Every further call creates an additional code; existing codes are kept.

After the first deployment of this extension:

```bash
docker compose up -d --build --wait backend frontend
docker compose exec -T frontend nginx -t
docker compose exec -T frontend nginx -s reload
```

After later creating/revoking a code, this is enough:

```bash
docker compose up -d --no-deps --wait backend
```

The short backend restart interrupts active requests: do not run it during an upload/import.
`REVIEW_ORIGIN`, `REVIEW_SESSION_SECRET` and `REVIEW_INVITES` are loaded from `.env`; without
`REVIEW_ORIGIN` this feature stays disabled. The admin allowlist never applies to reviewer sessions.

## 2. Cloudflare: second route, no change to the private Access policy

In the **existing tunnel**, add another published application route:

| Field | Value |
|---|---|
| Subdomain | `review` |
| Domain | `prodigi-marburg.de` |
| Path | empty |
| Service URL | `http://frontend:80` |
| Protect with Access | **off for this reviewer route**; here the app authenticates itself |

Do not create an Access mail-code application for this reviewer host and **do not add a Bypass/Everyone rule**
to the private ALITA application. If account-wide "Require Access protection" is active,
this separate app login must be explicitly accounted for in the Cloudflare configuration;
do not loosen the protection of the private application globally.

Enable Always Use HTTPS and Cache Bypass for the reviewer host. nginx additionally enforces HTTPS
based on the visitor protocol set by Cloudflare, rate-limits login requests and accepts at most
1 KiB of request body there. The API/download check applies regardless of visible UI buttons.

## 3. Test and hand-over

- Open `https://review.prodigi-marburg.de` in a private window: redirect to the code entry.
- Wrong/expired code: no access; correct code: app without admin rights.
- Download a document and chat with your own key. No changes/uploads possible.
- Log out: `/api/me` and downloads are blocked again without a valid cookie.
- The private URL is still reachable only with the Cloudflare mail code.

Then pass the URL and the code to the editorial office **separately from public materials**.
For downloads to work, the original files must also be on the server;
a Qdrant migration export alone is not enough.

## Revoking

```bash
python3 tools/reviewer_invites.py --revoke <Invitation-ID>
docker compose up -d --no-deps --wait backend
```

After the restart, existing sessions of this code are invalid too. Changing
`REVIEW_SESSION_SECRET` invalidates all reviewer sessions. To switch off all reviewers,
empty `REVIEW_ORIGIN` and recreate the backend; the private Cloudflare login stays in place.
