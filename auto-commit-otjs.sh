#!/usr/bin/env bash



# Directory and file to monitor
DIRECTORY="/home/asad/PersonalProjects/Python/otj-puncher"
FILE="main.py"

# Command to run when the program exits with status 0
COMMAND_TO_RUN='cd /home/asad/PersonalProjects/Python/otj-puncher && push "OTJS updated at $(date) "'

# Wait for the file to be executed and exit
echo "Monitoring $FILE for execution..."

while true; do
    # Use inotifywait to watch for any access event (file execution)
    inotifywait -e open "$DIRECTORY/$FILE"  # This watches when the file is opened (likely when it's executed)

    echo "$FILE has been executed. Monitoring its process..."

    # Wait for the main.py process to finish
    pid=$(pgrep -f "$DIRECTORY/$FILE")  # Find the process ID (PID) of main.py

    if [ -n "$pid" ]; then
        # Wait for the process to finish
        wait $pid
        exit_status=$?

        # Check the exit status of the main.py process
        if [ $exit_status -eq 0 ]; then
            echo "$FILE exited with status 0, running the script..."
            eval "$COMMNAND_TO_RUN"
        else
            echo "$FILE did not exit successfully."
        fi
    fi

    # Optionally, add a short delay before checking again
    sleep 10
done
