#!/usr/bin/env bash

set -euo pipefail

# 1. Check if git is already installed in the executable PATH
if command -v git &> /dev/null; then
    echo "Git is already installed: $(git --version)"
    exit 0
fi

echo "Git not found in PATH. Detecting operating system..."

# Function to attempt elevation if not running as root
sudo_cmd() {
    if [ "$EUID" -ne 0 ]; then
        if command -v sudo &> /dev/null; then
            sudo "$@"
        else
            echo "Error: Root privileges required, but 'sudo' is not installed." >&2
            exit 1
        fi
    else
        "$@"
    fi
}

# 2. Detect OS / Package Manager and install
install_git() {
    # Check macOS first
    if [ "$(uname)" = "Darwin" ]; then
        echo "Detected macOS."
        if command -v brew &> /dev/null; then
            echo "Installing Git via Homebrew..."
            brew install git
        else
            echo "Installing Xcode Command Line Tools (includes Git)..."
            xcode-select --install
        fi
        return 0
    fi

    # Check Linux distributions via /etc/os-release
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            ubuntu|debian|pop|mint)
                echo "Detected Debian-based system ($NAME)."
                sudo_cmd apt-get update && sudo_cmd apt-get install -y git
                ;;
            fedora|rhel|centos|rocky|alma|almalinux)
                echo "Detected Red Hat-based system ($NAME)."
                if command -v dnf &> /dev/null; then
                    sudo_cmd dnf install -y git
                else
                    sudo_cmd yum install -y git
                fi
                ;;
            arch|manjaro)
                echo "Detected Arch-based system ($NAME)."
                sudo_cmd pacman -Sy --noconfirm git
                ;;
            alpine)
                echo "Detected Alpine Linux."
                sudo_cmd apk add --no-cache git
                ;;
            *)
                echo "Unsupported OS ID: $ID" >&2
                return 1
                ;;
        esac
    else
        echo "Could not detect OS type (/etc/os-release missing)." >&2
        return 1
    fi
}

# Run installer
install_git

# Verify installation
if command -v git &> /dev/null; then
    echo "Git successfully installed: $(git --version)"
else
    echo "Installation finished, but 'git' command still not found." >&2
    exit 1
fi