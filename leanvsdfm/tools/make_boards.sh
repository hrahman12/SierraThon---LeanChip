#!/usr/bin/env bash
# Rebuild every board from the netlist: our board (compact hexagon) and the four fault boards
# (same placement, one mistake each), then regenerate the Lean data modules.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/build_pcb.py pcb/sierrathon_grid.kicad_pcb > /dev/null
python3 tools/layout_pcb.py pcb/sierrathon_grid.kicad_pcb pcb/sierrathon.kicad_pcb
python3 tools/extract_pcb.py pcb/sierrathon.kicad_pcb PcbData
for f in narrow_flash led_reversed wrong_cap_size flash_pins_swapped; do
  python3 tools/build_pcb.py /tmp/_fault_grid.kicad_pcb --fault "$f" > /dev/null
  python3 tools/layout_pcb.py /tmp/_fault_grid.kicad_pcb "pcb/fault_$f.kicad_pcb" --like pcb/sierrathon.kicad_pcb
  mod=$(python3 -c "print('PcbFault'+''.join(w.title() for w in '$f'.split('_')))")
  python3 tools/extract_pcb.py "pcb/fault_$f.kicad_pcb" "$mod"
done
rm -f /tmp/_fault_grid.kicad_pcb pcb/*.kicad_pro pcb/*.kicad_prl
