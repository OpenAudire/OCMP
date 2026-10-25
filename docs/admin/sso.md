# Single sign-on (OIDC)

OCMP can let people sign in with their university account through OpenID Connect, for
example with Microsoft Entra ID. Local passwords keep working beside it. SAML 2.0 is
planned for Phase 2.

## How accounts are matched

- A person is identified by the identity provider and their subject id at that provider,
  **never by email address**. Email addresses can be changed at the provider, so trusting
  them would let someone take over another person's account.
- With automatic account creation (the default), the first sign-in creates an OCMP account
  without a password. New accounts have **no roles**: an admin gives them access
  afterwards (see [Users and roles](users-and-roles.md)).
- If the email address of a first SSO sign-in already belongs to a local OCMP account,
  the sign-in is refused. Linking existing
  local accounts to SSO is not available yet. Create admin accounts with an address that
  people will not use for SSO, or use SSO accounts and give them roles after their first
  sign-in.

## 1. Register OCMP with the identity provider

Register OCMP as a **confidential web application** with:

| Value | Setting |
|---|---|
| Redirect URI | `https://<your site>/api/v1/auth/oidc/callback` (exactly, with your `PUBLIC_URL`) |
| Grant type | Authorization code (OCMP also uses PKCE) |
| Scopes | `openid profile email` |
| Client authentication | Client secret (`client_secret_post` or `client_secret_basic`) |

Note the **discovery URL** (ending in `/.well-known/openid-configuration`), the **client
id** and the **client secret**. The discovery URL must use HTTPS.

### Microsoft Entra ID

Following Microsoft's guide
[Register an application](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app):

1. In the Microsoft Entra admin center, open **App registrations** and choose
   **New registration**.
2. Name: for example "OCMP Curriculum Mapping". Supported account types: **accounts in
   this organizational directory only** (single tenant).
3. Redirect URI: platform **Web**, `https://<your site>/api/v1/auth/oidc/callback`.
4. After registering, copy the **Application (client) ID** and the **Directory (tenant)
   ID** from the overview.
5. Under **Certificates & secrets**, create a client secret and copy its **Value** (not the
   secret ID). Note when it expires: sign-in stops working on that day unless you create a
   new secret and update `.env` first.
6. Optional: under **Token configuration**, add the optional claim `email` to the ID
   token. Without it OCMP uses the sign-in name (`preferred_username`) as the email
   address when it looks like one.

The discovery URL is tenant-specific:
`https://login.microsoftonline.com/<tenant id>/v2.0/.well-known/openid-configuration`.
The multi-tenant `/common` and `/organizations` endpoints are not supported.

## 2. Configure OCMP

Add to `deploy/.env`:

```ini
OIDC_ENABLED=true
OIDC_PROVIDER_NAME=University account
OIDC_DISCOVERY_URL=https://login.microsoftonline.com/<tenant id>/v2.0/.well-known/openid-configuration
OIDC_CLIENT_ID=<client id>
OIDC_CLIENT_SECRET=<client secret value>
# Optional
# OIDC_SCOPES=openid profile email
# OIDC_AUTO_PROVISION=true
```

`OIDC_PROVIDER_NAME` is shown on the sign-in button ("Sign in with University account").
`OIDC_AUTO_PROVISION=false` allows only people who already have an SSO account in OCMP.
SSO accounts cannot be created in advance yet, so in practice it stops new people
signing in; leave it on and control access through roles.

Apply the change:

```bash
docker compose up -d
```

## 3. Test

Open the sign-in page in a private browser window: the SSO button should appear. Sign in
with a test account. Afterwards it appears in the user list without roles.

If sign-in fails, the sign-in page shows a short reason and the details are in
`docker compose logs api` (search for `oidc`). Common causes:

| Message on the sign-in page | Likely cause |
|---|---|
| "Single sign-on is not available right now" | An `OIDC_*` setting is missing, or the server cannot reach the discovery URL |
| "Single sign-on did not complete" | Redirect URI does not match exactly, wrong or expired client secret, or the server clock is wrong |
| "The sign-in took too long or was opened in another browser" | The sign-in was not finished within 10 minutes, or started in a different browser |
| "An account with your email address already exists" | A local account has the same email address (see [How accounts are matched](#how-accounts-are-matched)) |
| "Your organisation did not share an email address" | The provider sent neither `email` nor an email-like `preferred_username` |
| "There is no OCMP account for you yet" | `OIDC_AUTO_PROVISION=false` and the person has never signed in with SSO |
| "This account is disabled" | An admin deactivated the account |
