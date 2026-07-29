# Source system-wide shell settings.
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

export DATA=/data

# Slurm's completion script assumes an interactive shell.
if [[ $- == *i* ]] && [ -d /etc/profile.d ]; then
    for profile_script in /etc/profile.d/*.sh; do
        if [ -r "$profile_script" ]; then
            . "$profile_script"
        fi
    done
    unset profile_script
fi
