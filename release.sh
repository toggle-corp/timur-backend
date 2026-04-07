#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export SCRIPT_DIR

function release_custom_hook {
    # shellcheck disable=SC2154
    echo "Running custom hook for ${version_tag}"

    msg="# managed by release.sh"
    # TODO: Do we need to do this... this invalidates the docker cache for each new release
    sed -E -i "s/^version = .* $msg$/version = \"${version_tag#v}\"  $msg/" "./pyproject.toml"
    uv sync
    git add ./pyproject.toml ./uv.lock

    sed -E -i "s/^version: .* $msg$/version: ${version_tag#v}-SET-BY-CICD  $msg/" "./helm/Chart.yaml"
    git add ./helm/Chart.yaml
}

export -f release_custom_hook
export START_COMMIT="ed944248282e099601ce15b4903fa6345c0b7845"
export RELEASE_CUSTOM_HOOK=release_custom_hook
export REPO_NAME=toggle-corp/timur-backend
export DEFAULT_BRANCH=develop
export VERSION_TAG_PREFIX_MODE=require

export GIT_CLIFF__REMOTE__GITHUB__OWNER=toggle-corp
export GIT_CLIFF__REMOTE__GITHUB__REPO=timur-backend

# Forward the argument - used for pre-fill version
"$SCRIPT_DIR/fugit/scripts/release.sh" "${@:-}"
