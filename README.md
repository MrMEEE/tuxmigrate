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

tuxmigrate-1.1.0-1.x86_64.rpm  ← produced by fpm
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
| [fpm](https://fpm.readthedocs.io/) | Building RPMs |
| Ansible ≥ 2.14 | On the **target** machine |

Install fpm:
```bash
gem install fpm
```
Remember to add your .bashrc (and update ruby version)
```
export PATH="$HOME/.local/share/gem/ruby/3.3.0/bin:$PATH"
```

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

Options (only needed the first time; values are remembered in `versions.json`):

```
--package-name NAME   RPM package name      (default: tuxmigrate)
--maintainer  EMAIL   RPM maintainer field  (default: tuxmigrate)
--description TEXT    RPM summary/description
```

This will:
- Bump the **minor** version (e.g. `1.0.0` → `1.1.0`).
- Move and rename files from `changes/` into `role/playbooks/`.
- Regenerate `role/tasks/main.yml`.
- Run `fpm` to produce `<package-name>-<version>-1.x86_64.rpm`.

### 3. Distribute & install

```bash
sudo dnf install ./tuxmigrate-1.1.0-1.x86_64.rpm
# or
sudo rpm -Uvh tuxmigrate-1.1.0-1.x86_64.rpm
```

The post-install script runs immediately and applies any unapplied changes.

### 4. Check status

```bash
./tuxmigrate status
```

---

## Project layout

```
tuxmigrate/
├── tuxmigrate            # CLI entry point (Python)
├── versions.json         # Version + playbook registry (auto-created on first build, git-ignored)
├── changes/              # Drop new task files here
├── role/
│   ├── meta/main.yml
│   ├── playbooks/        # All versioned task files (managed by tuxmigrate)
│   └── tasks/main.yml    # Auto-generated — do not edit
├── site.yml              # Ansible playbook run by post-install
├── post-install.sh       # RPM post-install script (used by fpm)
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
- Edit **`versions.json`** directly to change package name, maintainer, or description at any time.
- `versions.json` is created automatically on the first `tuxmigrate build` and is git-ignored.
- The `role/` directory is committed to version control; `*.rpm` files are git-ignored.
- To target a non-`x86_64` architecture, pass `--architecture` to fpm or set it in a wrapper script.
