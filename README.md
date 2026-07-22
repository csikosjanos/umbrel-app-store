# csikosjanos-umbrel-app-store

A personal [Umbrel](https://umbrel.com) community app store.

Add it in Umbrel: **App Store → ⋯ → Community App Stores → Add** →
`https://github.com/csikosjanos/umbrel-app-store`

## Apps

### GitHub Runner (`csikosjanos-github-runner`)

A self-hosted GitHub Actions **organisation** runner, packaged as an Umbrel app
so umbreld manages it and it survives reboots / OTA updates (a manually started
container is removed by umbreld on every boot).

**Secrets are NOT stored in this repo.** After installing the app, provide the
org name and a GitHub PAT via the app's runtime `.env`:

```sh
# on the Umbrel box
sudo tee /home/umbrel/umbrel/app-data/csikosjanos-github-runner/.env >/dev/null <<'EOF'
ORG_NAME=YourOrg
ACCESS_TOKEN=github_pat_xxx   # fine-grained PAT: Org → Self-hosted runners = Read/Write
EOF
sudo chmod 600 /home/umbrel/umbrel/app-data/csikosjanos-github-runner/.env
# then restart the app from the Umbrel UI (or reinstall)
```

Target the runner from workflows:

```yaml
jobs:
  build:
    runs-on: [self-hosted, umbrel]
```

The runner image (`myoung34/github-runner`) is minimal — jobs should install
their own toolchains via `actions/setup-node`, `actions/setup-python`, etc.
