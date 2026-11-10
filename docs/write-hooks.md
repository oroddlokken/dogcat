# Write hooks

On POSIX systems, dogcat can validate pending records with an optional
`pre_write_hook`. It is off by default and accepts any trusted validator.

## Gitleaks example

On macOS, install Gitleaks and enable secret scanning:

```sh
brew install gitleaks
dcat config set --global pre_write_hook 'gitleaks stdin --no-banner --redact --ignore-gitleaks-allow'
dcat config get --global pre_write_hook
```

Try a clean write and a synthetic secret in a temporary store:

```sh
(
  tmp=$(mktemp -d)
  cd "$tmp" || exit 1
  dcat init --dogcats-dir "$tmp/store" --namespace trial --no-git
  dcat create 'Clean trial issue' --dogcats-dir "$tmp/store"
  prefix=ghp_
  body=Zx81Kq0LmT4vR7nB2cYw9sHd5jFg3aPe6uQi
  dcat create 'Synthetic secret' --description "${prefix}${body}" --dogcats-dir "$tmp/store"
  echo "Exit: $?"
  rm -rf "$tmp"
)
```

The clean issue is created. The synthetic secret is rejected with
`Error: pre_write_hook rejected the write (exit 1)` and `Exit: 1`.
Disable the hook with `dcat config unset --global pre_write_hook`.

The command is user-global and applies across stores. It lives in
`$XDG_CONFIG_HOME/dogcat/config.toml`, defaulting to
`~/.config/dogcat/config.toml`; repository and local config cannot select it.
It runs as a shell command, so configure only commands you trust. For another
validator, see the [acceptance-criteria example](../examples/hooks/require_acceptance.py).

## Contract and scope

Dogcat sends each pending batch as unmodified JSONL on stdin. A batch can
contain multiple data and event records; events can include old values, so a
scanner may reject removal of a secret. The hook cannot transform the write.
Exit 0 approves; any other exit, failure to start, invalid global config, or
30-second timeout rejects it. Dogcat hides stdout and stderr. The hook inherits
the working directory and environment; `DCAT_WRITE_TARGET` is the absolute
path of the target file.

Approval covers a batch, not an entire command or multiple files: earlier
batches may already be written. Hooks do not scan history or cover Git, manual
edits, compaction, merge, archive, or repair. Keep hooks fast and side-effect
free; approval does not guarantee the subsequent write succeeds.

For exit 127, check paths, permissions and shell quoting. For a timeout or
other rejection, run the validator directly with synthetic JSONL and check its
exit code. For invalid config, check the TOML and ensure the value is a string.
