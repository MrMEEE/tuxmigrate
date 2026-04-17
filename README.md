# tuxmigrate

> RPM-based Ansible configuration migration tool — like Alembic, but for system configuration.

tuxmigrate keeps laptops and servers in sync by packaging versioned Ansible task files into an RPM. Installing the RPM on any machine automatically applies all changes that haven't been run there yet.

---

## How it works

```
changes/              ← you drop task files here
    └── install_vim.yml

tuxmigrate build      ← run this when ready

role/playbooks/       ← files are moved here and versioned
    └── 1.1.0_01_install_vim.yml

tuxmigrate-1.1.0-1.x86_64.rpm  ← produced by fpm or rpmbuild
```

When the RPM is **installed or upgraded**:
1. The `%post` scriptlet calls `ansible-playbook site.yml --connection=local`.
2. The role iterates all versioned task files **in order** (oldest → newest).
3. For each task file, it checks for a **local fact** in `/etc/ansible/facts.d/`.
4. If the fact does **not** exist, the tasks are run and the fact is written on success.
5. Files that have already been applied are silently skipped.

This means installing a newer RPM on a machine that already has an older version will only apply the *new* changes.

---

## Requirements

| Tool | Purpose |
|------|---------|
| Python ≥ 3.10 | Running `tuxmigrate` |
| [fpm](https://fpm.readthedocs.io/) | Default RPM builder |
| `rpmbuild` | Optional native RPM builder |
| Ansible ≥ 2.14 | On the **target** machine |

Install the default builder:
```bash
gem install fpm
```
Remember to add your .bashrc (and update ruby version)

```bash
export PATH="$HOME/.local/share/gem/ruby/3.3.0/bin:$PATH"
```

If you prefer the native RPM toolchain, install `rpmbuild` and build with `--builder rpmbuild`.

---

## Workflow

### 1. Write a change

Create a standard Ansible **task file** (not a full playbook) in `changes/`:

```yaml
# changes/install_vim.yml
- name: Install vim
  ansible.builtin.package:
    name: vim
    state: present
```

> **Task files vs. playbooks:** files in `changes/` must be lists of tasks (no `hosts:` key), because they are `include_tasks`-ed inside a role. Think of them as the body of a `tasks:` block.

You can add multiple files; they will be applied in alphabetical order within a build.

### 2. Build

```bash
./tuxmigrate build
```

Options (values are remembered in `config.json` unless overridden):

```
--package-name NAME   RPM package name      (default: tuxmigrate)
--maintainer  EMAIL   RPM maintainer field  (default: tuxmigrate)
--description TEXT    RPM summary/description
--builder     BUILDER RPM builder backend   (fpm or rpmbuild)
--push                 Upload built RPM to Satellite/Katello
--no-push              Skip Satellite/Katello upload for this build
```

This will:
- Bump the **patch** version by default (e.g. `1.0.0` → `1.0.1`).
- Move and rename files from `changes/` into `role/playbooks/`.
- Regenerate `role/tasks/main.yml`.
- Build `<package-name>-<version>-1.*.rpm` with `fpm` by default, or `rpmbuild` if configured.

### 2a. Configure non-interactively (recommended)

Use `tuxmigrate config` to create or update `config.json` without manual editing:

```bash
# Create config.json (if missing) and print it
./tuxmigrate config --init --show

# Set package/build defaults
./tuxmigrate config \
    --package-name tuxmigrate \
    --maintainer ops@example.com \
    --description "TuxMigrate configuration management" \
    --builder fpm

# Set Satellite/Katello settings
./tuxmigrate config \
    --satellite-servername https://satellite.example.com \
    --satellite-username admin \
    --satellite-password 'secret' \
    --satellite-repository-id 123 \
    --satellite-verifyssl \
    --satellite-auto-push

# View current config (password redacted)
./tuxmigrate config --show
```

You can still edit `config.json` manually if preferred.

### 3. Optional Satellite/Katello upload

To upload RPMs automatically after each successful build, add a `satellite` section to `config.json`:

```json
{
    "version": "1.0.1",
    "package_name": "tuxmigrate",
    "maintainer": "tuxmigrate",
    "description": "TuxMigrate configuration management",
    "require_tuxpatch": false,
    "builder": "fpm",
    "playbooks": [],
    "satellite": {
        "auto_push": true,
        "servername": "https://satellite.example.com",
        "username": "admin",
        "password": "secret",
        "verifyssl": true,
        "repository_id": "123"
    }
}
```

Required Satellite/Katello fields:

- `servername`
- `username`
- `password`
- `verifyssl`
- `repository_id`

Set `satellite.auto_push` to `true` to upload automatically on every build, or keep it `false` and use `./tuxmigrate build --push` when needed.

### 4. Distribute & install

```bash
sudo dnf install ./tuxmigrate-1.1.0-1.x86_64.rpm
# or
sudo rpm -Uvh tuxmigrate-1.1.0-1.x86_64.rpm
```

The post-install script runs immediately and applies any unapplied changes.

### 5. Check status

```bash
./tuxmigrate status
```

---

## Project layout

```
tuxmigrate/
├── tuxmigrate            # CLI entry point (Python)
├── config.json           # Version/build/Satellite config (auto-created on first build, git-ignored)
├── changes/              # Drop new task files here
├── role/
│   ├── meta/main.yml
│   ├── playbooks/        # All versioned task files (managed by tuxmigrate)
│   └── tasks/main.yml    # Auto-generated — do not edit
├── site.yml              # Ansible playbook run by post-install
├── post-install.sh       # Reference/runtime script; build backends generate their own embedded %post script
└── .gitignore
```

---

## Local fact format

Each applied task file leaves a JSON fact at:

```
/etc/ansible/facts.d/tuxmigrate_<sanitized_name>.fact
```

Example (`tuxmigrate_1_1_0_01_install_vim.fact`):
```json
{"applied": true, "playbook": "1.1.0_01_install_vim.yml"}
```

---

## Tips

- **Re-running** `tuxmigrate build` with nothing in `changes/` will error — this prevents accidental empty RPMs.
- Set `require_tuxpatch` in `versions.json` to control RPM dependency metadata:
    - `false` (default): no tuxpatch dependency
    - `true`: adds `Requires: tuxpatch`
    - `"1.2.3"`: adds `Requires: tuxpatch >= 1.2.3`
- Edit **`config.json`** directly to change package name, maintainer, builder, or Satellite/Katello upload settings.
- `config.json` is created automatically on the first `tuxmigrate build` and is git-ignored.
- The `role/` directory is committed to version control; `*.rpm` files are git-ignored.
- `post-install.sh` behavior remains the runtime reference, but builds do not read this file directly anymore.
- Existing `versions.json` files are migrated automatically to `config.json`.
