#!/bin/bash
# Move to the live directory
cd /home/howl/Piccolo

OLD_SHA=$1
NEW_SHA=$2

# Pull latest code from GitLab
git pull

# Detect changed directories
CHANGED_DIRS=$(git diff --name-only $OLD_SHA $NEW_SHA | cut -d/ -f1 | sort -u)

DEPLOYED_PROJECTS=""
SERVICES_TO_BUILD=""

for DIR in $CHANGED_DIRS; do
    case "$DIR" in
        "Family_Dashboard")
            SERVICES_TO_BUILD="$SERVICES_TO_BUILD family_dashboard"
            DEPLOYED_PROJECTS="$DEPLOYED_PROJECTS\n- Family Dashboard"
            ;;
        "Game_Scanner")
            SERVICES_TO_BUILD="$SERVICES_TO_BUILD game_scanner_api game_scanner_daemon game_scanner_ui"
            DEPLOYED_PROJECTS="$DEPLOYED_PROJECTS\n- Game Scanner Stack"
            ;;
        "Crunchyroll_Scanner"|"Crunchyroll_API"|"Crunchyroll_UI")
            SERVICES_TO_BUILD="$SERVICES_TO_BUILD crunchyroll_scanner crunchyroll_api crunchyroll_ui"
            DEPLOYED_PROJECTS="$DEPLOYED_PROJECTS\n- Crunchyroll Stack"
            ;;
        "Weather_Daemon"|"Weather_API")
            SERVICES_TO_BUILD="$SERVICES_TO_BUILD weather_brief_daemon weather_api"
            DEPLOYED_PROJECTS="$DEPLOYED_PROJECTS\n- Weather Stack"
            ;;
        "Flight_Tracker"|"Flight_API"|"Maverick_FE")
            SERVICES_TO_BUILD="$SERVICES_TO_BUILD flight_tracker_daemon flight_api maverick_front_end"
            DEPLOYED_PROJECTS="$DEPLOYED_PROJECTS\n- Flight Tracking Stack"
            ;;
        "docker-compose.yml")
            SERVICES_TO_BUILD="ALL"
            DEPLOYED_PROJECTS="$DEPLOYED_PROJECTS\n- Core Infrastructure"
            ;;
    esac
done

# Execute builds
if [ "$SERVICES_TO_BUILD" == "ALL" ]; then
    docker compose up -d --build
elif [ -n "$SERVICES_TO_BUILD" ]; then
    docker compose up -d --build $SERVICES_TO_BUILD
else
    DEPLOYED_PROJECTS="\n- Maintenance / Minor File Updates (No Containers Rebuilt)"
fi

# Send Discord Alert
PAYLOAD=$(cat <<EOF
{
  "embeds": [{
    "title": "🚀 Piccolo Deployment Successful",
    "color": 3066993,
    "description": "**Deployed Projects:**$DEPLOYED_PROJECTS"
  }]
}
EOF
)
curl -H "Content-Type: application/json" -d "$PAYLOAD" $DISCORD_DEPLOY_WEBHOOK