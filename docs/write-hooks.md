# Write hooks

A user-global `pre_write_hook` can validate a pending write on POSIX systems. It is optional: an unset or blank value disables it. No scanner is required, and a disabled hook starts no subprocess. Configure a command you trust in your user-global config, for example:

```sh
dcat config set --global pre_write_hook 'python3 /absolute/path/to/require_acceptance.py'
```

Disable it with `dcat config unset --global pre_write_hook`. Use an absolute path and shell-quote paths containing spaces. The command is a shell command, so only set it in your own global config; repository config cannot select it. A global wrapper can dispatch by namespace if different stores need different policies. `DCAT_WRITE_TARGET` contains the absolute planned target path.

The hook receives JSONL on stdin: a batch of data records and event records, not the whole database. An issue data record is the new state; events can contain old values. A scanner can therefore reject removal of a pre-existing secret when an event retains it. Exit 0 allows the write; any other exit, a start failure, a 30-second timeout, or invalid configuration rejects it. Output on stdout and stderr is discarded to avoid leaking secrets; an error reports the exit code when available.

The batch is validated at flush, not as a transaction across multiple commands or stores. Newly generated namespace mutations are also validated. Historical copies, compaction, merge, archive, repair, and external writes are not retroactively scanned or sanitized.

Hooks should be fast local validators without side effects. They cannot transform the write and are not intended for notifications, deployments, or test runs. The standalone [acceptance example](../examples/hooks/require_acceptance.py) requires nonempty acceptance text on every `in_progress` issue record, including edits to issues already in progress, while ignoring events and other record types. It exits 10 when acceptance is missing and 1 for invalid JSON or a non-object record. This illustrates a workflow policy beyond secret scanning.

For example, configure a locally installed and trusted `gitleaks` scanner to inspect stdin:

```sh
dcat config set --global pre_write_hook 'gitleaks stdin --no-banner --redact'
```

Test the scanner and its configuration locally; dogcat does not install or depend on it. Remember that event history can include old values.
