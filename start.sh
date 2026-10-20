
#!/bin/bash

cd "$HOME/Documents/dmr/testDMR" || exit 1

gnome-terminal --title="DMR Scanner" -- bash -c '
cd "$HOME/Documents/dmr/testDMR"
./venv/bin/uvicorn main:app --reload
echo
echo "Server berhenti. Tekan Enter untuk menutup."
read
'

