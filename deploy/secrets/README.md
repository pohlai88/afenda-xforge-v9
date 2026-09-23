# deploy/secrets

Secret files for the compose stack. Everything here except this README and
`.gitignore` is ignored by git; never commit a value.

Generate them with `deploy/make-secrets.sh` after building the image. It writes
only the files that are missing:

| File | Used by | Content |
|---|---|---|
| `db_password` | db, init, xforge | password of the PostgreSQL role `xforge` |
| `admin_password` | init | password `db init` gives the `admin` login |
| `master_password` | the operator only | database-manager master password |
| `master_password_hash` | init, xforge | pbkdf2_sha512 hash of it (`admin_passwd`) |

`db_password` is written into the PostgreSQL volume the first time `db` starts.
Changing the file afterwards does not change the role's password; change it
with `ALTER ROLE xforge PASSWORD ...` first, then update the file.
