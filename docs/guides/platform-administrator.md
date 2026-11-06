# Guide: platform administrator

You run the installation and hold every permission. Day-to-day curriculum work belongs to the other roles.

## First steps

1. **Install** with the [install guide](../operations/install.md) and run the first-run setup. Then read [Admin
   basics](../admin/basics.md#first-steps-after-setup).
2. **Set the institution's words and profile** under Admin > Institution settings (for example Course for
   Module, the health profile, the default taxonomy scale) and the numbers behind mapping, credits, quality
   checks and coverage. Set the **time zone** in `.env` if not South African
   ([Configuration](../operations/configuration.md)).
3. **Give people access** under Admin > People and Roles, or let them sign in with the university account
   ([Single sign-on](../admin/sso.md), [Users and roles](../admin/users-and-roles.md)).

## Ongoing

* **AI** is off by default. To switch it on, follow [Setting up an AI provider](../admin/ai-setup.md); check it
  with [Checking the AI's mapping](../admin/ai-evaluation.md).
* **Embeddings** (optional) give meaning-based search and near-duplicate checks
  ([Embeddings](../operations/embeddings.md)).
* **Back up** and test a restore ([Backup and restore](../operations/backup-restore.md)); **upgrade** with
  [Upgrade](../operations/upgrade.md).
* **Audit log** and retention: [Admin basics](../admin/basics.md#audit-log).
* **API tokens** for scripts: [API tokens](../admin/api-tokens.md).
* **Personal data**: the [data inventory](../privacy/data-inventory.md) and the [privacy notice
  template](../privacy/privacy-notice-template.md).
* **The demo**: load it for a trial (`load-demo`) and remove it before real use (`remove-demo`, a dry run unless
  `--apply`).
