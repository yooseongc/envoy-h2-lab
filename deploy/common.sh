# Shared by the Bash lifecycle commands after changing to the installation directory.
check_project() {
    local containers id directory
    containers=$(docker ps -aq --filter label=com.docker.compose.project=envoy-h2-lab --filter label=com.docker.compose.service=ui)
    for id in $containers; do
        directory=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$id")
        if [[ -n $directory && $directory != "$(pwd -P)" ]]; then
            echo "Another installation owns this project: $directory" >&2
            exit 1
        fi
    done
}
worker_ids() {
    docker ps "$1" --no-trunc --filter label=lab.project=envoy-h2-lab
}
saved_workers() {
    if [[ -s .stopped-workers.json ]]; then
        tr -d '[]"[:space:]' < .stopped-workers.json | tr ',' '\n'
        echo
    fi
}
