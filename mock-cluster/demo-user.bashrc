# Source system-wide shell settings.
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

export DATA=/data
export SCRATCH=/scratch/demo_user
export ARCHIVE=/archive/demo_user
export EPISODE_WORK=/episode/work
export CODEX_MODEL="${CODEX_MODEL:-gpt-5.6-terra}"

# Slurm's completion script assumes an interactive shell.
if [[ $- == *i* ]] && [ -d /etc/profile.d ]; then
    for profile_script in /etc/profile.d/*.sh; do
        if [ -r "$profile_script" ]; then
            . "$profile_script"
        fi
    done
    unset profile_script
fi
