# Upstream Sync Tracking

This file tracks synchronization status with [canonical/concierge](https://github.com/canonical/concierge) (the Go implementation).

**Last sync check:** 2026-06-28
**Baseline:** concierge-py created 2024-10-10, syncing changes after that date

## Pending Changes

All changes have been ported. See branches below for PRs.

### Open PRs

| PR | Branch | Go Commit | Description |
|----|--------|-----------|-------------|
| [#12](https://github.com/tonyandrewmeyer/concierge-py/pull/12) | `feat/presets-as-yaml` | `b28b069` | Store presets as YAML rather than Python/Pydantic |
| [#13](https://github.com/tonyandrewmeyer/concierge-py/pull/13) | `ci/avoid-unnecessary-k8s-microk8s` | `f33c1e8`, `976a441` | Avoid using K8s/MicroK8s as provider unless explicitly testing |
| [#14](https://github.com/tonyandrewmeyer/concierge-py/pull/14) | `feat/image-registry-config` | `d844183` | Add image registry configuration for K8s and MicroK8s |
| [#15](https://github.com/tonyandrewmeyer/concierge-py/pull/15) | `feat/dry-run` | `bebf251` | Add --dry-run flag to prepare and restore commands |
| [#16](https://github.com/tonyandrewmeyer/concierge-py/pull/16) | `refactor/simplify-system-interface` | `1ac1573` | Simplify system interface, replacing methods with helpers |
| [#17](https://github.com/tonyandrewmeyer/concierge-py/pull/17) | `fix/snap-channel-defaults` | `2145dd1`, `31f4330`, `0c6c5f9` | Snaps with no explicit channel default to latest/stable |
| [#18](https://github.com/tonyandrewmeyer/concierge-py/pull/18) | `feat/dev-preset-astral-uv` | `6d63fc2` | Add astral-uv to the dev preset |
| [#19](https://github.com/tonyandrewmeyer/concierge-py/pull/19) | `fix/containerd-pre-bootstrap-only` | `0ddf24c` | Only remove /run/containerd if we need to bootstrap k8s |
| [#20](https://github.com/tonyandrewmeyer/concierge-py/pull/20) | `fix/disabled-snap-handling` | `86b1b21` | Treat non-active installed snaps as installed |
| [#21](https://github.com/tonyandrewmeyer/concierge-py/pull/21) | `feat/juju-snap-revision` | `2f64cda` | Allow specifying a Juju snap revision |
| [#25](https://github.com/tonyandrewmeyer/concierge-py/pull/25) | `ci/conventional-pr-title-local-script` | `814f3a6` | Replace third-party PR-title action with a local Python script |
| [#26](https://github.com/tonyandrewmeyer/concierge-py/pull/26) | `ci/dependency-review-action` | `4fd2092` | Add dependency-review-action on PRs |
| [#28](https://github.com/tonyandrewmeyer/concierge-py/pull/28) | `ci/dependency-review-no-pr-comment` | `d8ca796` | Drop PR-comment summary from dependency-review workflow |
| [#30](https://github.com/tonyandrewmeyer/concierge-py/pull/30) | `fix/microk8s-image-registry-race` | `c1ed8cf` | Wait for MicroK8s to settle before configuring image registry |
| [#31](https://github.com/tonyandrewmeyer/concierge-py/pull/31) | `chore/rename-zizmor-yaml` | `049b39a` | Rename `.github/zizmor.yml` to `.github/zizmor.yaml` |

### Previously Merged

| Branch | Go Commit | Description |
|--------|-----------|-------------|
| `feat/add-gnome-keyring` | `5be986a` | Add gnome-keyring to default packages for craft tools |
| `feat/handle-existing-containerd` | `8c5fdea` | Transparently handle existing containerd services for k8s |
| `feat/auto-set-model-arch-constraint` | `6205598` | Auto-set model architecture constraint for initial models |
| `fix/symlink-chown` | `39a18ff` | Don't dereference symlinks in recursive ownership change |
| `feat/show-command-timing` | `6bd43c7` | Show time taken for each command in verbose mode |
| `fix/check-bootstrapped-error` | `63c74a3` | Look for more specific error in checkBootstrapped |

### Already Implemented (No Action Needed)

| Go Commit | Description | Notes |
|-----------|-------------|-------|
| `1dca9d2` | Avoid LXD stop to speed up subsequent prepare calls | Already in `_workaround_refresh()` |
| `bce5101` | Avoid waiting indefinitely for providers | Already have `--timeout` flags |
| `00102fd` | Install iptables for k8s provider if not present | Already in k8s provider |
| `158c3a7` | Ensure LXD is started again after refresh | Already in `_install()` |
| `fea22ef` | Workaround LXD refresh issue | Already in `_workaround_refresh()` |
| `276edb8` | Use MicroK8s config for model defaults and bootstrap constraints | Python `MicroK8s.__init__` already reads from `config.providers.microk8s` (the upstream bug was a Go copy-paste from `config.Providers.Google`) |
| `6307920` | Merge provider credentials instead of overwriting | Python `build_credentials_yaml` already sets per-cloud keys on the inner map rather than replacing it |
| `5b915d8` | Fall back to getent for users not in /etc/passwd | Python's `pwd.getpwnam` calls libc and already consults NSS (SSSD/LDAP) on systems where it's configured |
| `f7b67a7` | Drop logs to trace if an error is expected | Python's runner only prints command output when `--trace` is set, so expected failures are already silenced by default |

## Previously Implemented

These features from the Go version were already implemented in concierge-py:

- `crafts` preset (`0738de0`)
- `juju.disable` option (`f7a839b`)
- `agent-version` for bootstrap (`723a397`)
- `extra-bootstrap-args` for bootstrap (`4d6726c`)
- Per-provider `model-defaults` and `bootstrap-constraints` (`864293b`)
- Snap `connections` (`da74f5a`)
- jhack in dev preset (`43a2ed7`, `d79dac7`)
- Google provider (`cdb2670`)
- Canonical K8s provider (`968ac9c`)
- `--trace` flag (`6ba7628`)
- Retryable commands (`e36799c`)

## Not Applicable

These changes don't apply to the Python implementation:

- `eb8b563` - Replace snapcore/snapd dependency (Python has its own implementation)
- `806de38` - Don't retry permanent `ErrNotInstalled` errors — depends on the `DryRunWorker` mechanism from #15, which is still an open PR; needs human review once that lands
- `e137417` - Minor Go linting cleanup
- `75e1947` - Zizmor workflow (concierge-py already has its own `zizmor.yaml`)
- `ea1a5ee` - Go static analysis workflow (golangci-lint, not applicable to Python)
- `e57ee40` - Spread integration test adjustment
- `00e4e48` - Dependabot cooldown tailored to Go's dependency stream
- `0b54dd0` - SECURITY.md PGP key update — concierge-py does not have a `SECURITY.md`
- `d6548eb` - Viper nil-value workaround (Viper is Go-specific; Python uses Pydantic)
- `89a3728` - Replace `cmdMu` + `map[string]*sync.Mutex` with `sync.Map.LoadOrStore` in `RunExclusive`, plus comments documenting Go pflag `Get*` error discards. The Go change is a Coverity-finding refactor with no behavioural change; Python's `run_exclusive` already uses an `asyncio.Lock` + dict pattern that is idiomatic and equivalent, and the pflag comments have no analogue in Typer-based code.
- `e904ac9`, `600fdca` - Release-time secscan / SBOM workflows for the Go binary
- `c3f5a01`, `25e26be`, `54cc160`, `0b0c130` - Go toolchain version bumps
- `3ef5241` - Add 386/armhf/riscv64 targets to `.goreleaser.yaml` (Python wheels don't use goreleaser)
- Various Go dependency bumps and GitHub Action version bumps (`43771aa`, `3ee502c`, `defca86`, `9c4a90b`, `cf9537c`, `c549727`, `aeda3bc`, `90530f3`, `ef54599`, `3d81a68`, `1978fec`, `47e975c`, `9997760`)
