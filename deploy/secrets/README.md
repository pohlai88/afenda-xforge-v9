# deploy/secrets

Secret files for the compose stack. Everything here except this README and
`.gitignore` is ignored by git; never commit a value.

Generate them with `deploy/make-secrets.sh` after building the image. It writes
the files that are missing **or empty**, so emptying one is how you ask for a
new value; a file that still holds a value is never overwritten.

| File | Used by | Content |
|---|---|---|
| `db_password` | db, backup/restore/migrate | password of the PostgreSQL role `xforge` |
| `db_app_password` | init, xforge | password of the role `afenda_app` the app connects as |
| `admin_password` | init, **first `db init` only** | password `db init` gives the `admin` login |
| `master_password` | the operator only | database-manager master password |
| `master_password_hash` | init, xforge | pbkdf2_sha512 hash of it (`admin_passwd`) |

`admin_password` is spent the moment the database is first initialised. From
then on nothing reads it — `init.sh` takes the `initialised` branch — and it is
**not** the current password of any account: the owner can change that password,
and the login itself can be renamed, without this file changing. Treating it as
a live credential is a trap, so empty it once a host is up rather than leaving a
stale value on disk. Keep the file itself: compose mounts it into `init` on
every `up`, and container creation fails outright if the path is missing
(`invalid mount config ... bind source path does not exist`). `init.sh` refuses
to run a first init against an empty one, so a rebuilt host must run
`make-secrets.sh` again first.

`db_password` is written into the PostgreSQL volume the first time `db` starts.
Changing the file afterwards does not change the role's password; change it
with `ALTER ROLE xforge PASSWORD ...` first, then update the file.
