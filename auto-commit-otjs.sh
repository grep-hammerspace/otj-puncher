#!/usr/bin/env bash

# Redirect stdout and stderr
LOG_FILE="/var/log/otj-autocommit.log"
exec >> "$LOG_FILE" 2>&1

echo "---------- Started at $(date) ----------"
# Directory and file to monitor
DIRECTORY="/home/asad/PersonalProjects/Python/otj-puncher"
FILE="main.py"

# Command to run when main.py exits with status 0
COMMAND_TO_RUN='cd /home/asad/PersonalProjects/Python/otj-puncher && git add otjs.csv && git commit -m "OTJS updated at $(date)" && git push'

echo "Monitoring $FILE for execution..."

while true; do
    # Monitor the file being accessed (likely executed)
    inotifywait -e access "$DIRECTORY/$FILE"

    echo "$FILE has been accessed. Checking if process is running..."

    # Get the PID of the running main.py process
    pid=$(pgrep -f "$DIRECTORY/$FILE" | head -n 1)

    if [ -n "$pid" ]; then
        echo "Found main.py process with PID $pid. Waiting for it to finish..."

        # Polling loop to wait for the process to exit
        while kill -0 $pid 2>/dev/null; do
            # Process is still running
            sleep 1
        done

        # After the process finishes, check the exit status
        exit_status=$?
        if [ $exit_status -eq 0 ]; then
            echo "$FILE exited successfully. Running post-command..."
            eval "$COMMAND_TO_RUN"
        else
            echo "$FILE did not exit successfully (status $exit_status)." >&2
        fi
    else
        echo "No running process found for $FILE." >&2
    fi

    sleep 1
done
