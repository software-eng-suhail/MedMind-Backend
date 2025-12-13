# Helper script to run a temporary Redis server using Docker (Windows PowerShell)
# Requires Docker Desktop to be installed and running.

$containerName = "medmind-redis"
$existing = docker ps -a --filter "name=$containerName" --format "{{.Names}}"
if ($existing -ne "") {
    Write-Host "Starting existing Redis container..."
    docker start $containerName
} else {
    Write-Host "Creating and starting Redis container..."
    docker run -d --name $containerName -p 6379:6379 redis:7
}
Write-Host "Redis should be available at redis://127.0.0.1:6379/"
Write-Host "To stop the container: docker stop $containerName"