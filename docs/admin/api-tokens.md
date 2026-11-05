# API tokens

A **personal API token** lets a script call the Curriculum in Context API as you, for example to download a
report every night. It can do no more than you can, and you choose how much less. The design is in
[ADR 060](../adr/060-admin-screens-api-tokens-remove-demo.md).

## Making one

Open **Account** (your name, top right) and press **Make a token**.

* **Name**: what it is for ("Nightly export"). You will see this in the list.
* **What it may do**: **Read** looks at things only; **Write** also changes things, as you could. Choose Read
  unless the script has to change something.
* **Lasts**: 7 to 365 days. A token that expires has to be replaced, which is the point: nothing stays valid
  by accident.

The token is shown **once**. Copy it then and keep it like a password. If you lose it, revoke it and make another:
it cannot be shown again, because only a fingerprint is stored. You can have 20 active tokens.

## Using one

Send it in a header on every request:

```
curl -H "Authorization: Bearer ocmp_..." https://curriculum.example.org/api/v1/programmes
```

The API is described at `/api/docs` (OpenAPI). A token gets exactly the answers you would get when signed in:
what you may not see is "not found" and what you may not do is refused.

A token can **not** be used to sign in to the web app, change your password or make more tokens: those need you
at the browser.

| Answer | Meaning |
|---|---|
| 401 | The token is wrong, revoked or expired, or your account is deactivated. |
| 403 "This token can only read." | A read token was used to change something. |
| 403 otherwise | You do not have the permission, as when signed in. |

## Keeping them safe

* Give each script its own token, so you can revoke one without stopping the others.
* The list shows each token's name, the first characters, what it may do, when it expires and **when it was last
  used**. A token that has never been used, or has not been used for months, can be revoked.
* **Revoke** a token the moment it may be lost. It stops working at once.
* When an account is **deactivated or deleted**, all of its tokens are revoked.
* Administrators (permission to manage users) can see and revoke another person's tokens on the person's page
  (Admin > People). They cannot see the tokens themselves.
* Making and revoking a token is recorded in the [audit log](basics.md#audit-log); using one is not (only the
  time it was last used is kept).

Webhooks (a message to your system when something happens) are planned for Phase 2.
