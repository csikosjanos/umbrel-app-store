# Loads the Settings saved in the firstmate web UI into this shell.
# Sourced by every bash: non-interactive via BASH_ENV, interactive via
# /etc/bash.bashrc. Keep it cheap and side-effect free.

# Login shells get PATH reset by /etc/profile; keep the persistent tool dirs
# (npm -g installs, ~/.local/bin installers) first so upgrades survive.
case ":$PATH:" in *":/root/.npm-global/bin:"*) ;; *) PATH="/root/.npm-global/bin:$PATH" ;; esac
case ":$PATH:" in *":/root/.local/bin:"*) ;; *) PATH="/root/.local/bin:$PATH" ;; esac
export PATH

if [ -r /settings/env.sh ]; then
  . /settings/env.sh
fi
