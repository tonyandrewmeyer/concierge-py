# Upstream Sync Tracking

This file tracks synchronization status with [canonical/concierge](https://github.com/canonical/concierge) (the Go implementation).

**Last sync check:** 2026-02-26
**Baseline:** concierge-py created 2024-10-10, syncing changes after that date

## Pending Changes

All changes have been ported. See branches below for PRs.

### Branches Ready for PR

| Branch | Go Commit | Description |
|--------|-----------|-------------|
| `feat/presets-as-yaml` | `b28b069` | Store presets as YAML rather than Python/Pydantic |
| `ci/avoid-unnecessary-k8s-microk8s` | `f33c1e8`, `976a441` | Avoid using K8s/MicroK8s as provider unless explicitly testing |
| `feat/image-registry-config` | `d844183` | Add image registry configuration for K8s and MicroK8s |
| `feat/dry-run` | `bebf251` | Add --dry-run flag to prepare and restore commands |
| `refactor/simplify-system-interface` | `1ac1573` | Simplify system interface, replacing methods with helpers |
| `fix/snap-channel-defaults` | `2145dd1`, `31f4330`, `0c6c5f9` | Snaps with no explicit channel default to latest/stable |

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
- Various Go dependency bumps
- Go-specific refactors
