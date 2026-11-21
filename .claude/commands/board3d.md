---
description: Export the board to 3D (STEP + GLB) and test it against Lean's placement
allowed-tools: Bash(kicad-cli:*), Bash(node leanvsdfm/tools/step_tool.mjs:*), Bash(python3 leanvsdfm/tools/check_step_agreement.py:*), Read
---
Turn the 2D board into a 3D model and check that Lean and KiCad agree on where every part is.

1. `cd leanvsdfm && KICAD6_3DMODEL_DIR=$PWD/models3d KICAD7_3DMODEL_DIR=$PWD/models3d kicad-cli pcb export step --subst-models -f -o out3d/sierrathon.step pcb/sierrathon.kicad_pcb`
2. `node tools/step_tool.mjs glb out3d/sierrathon.step out3d/sierrathon.glb out3d/sierrathon_parts.json` (needs `npm i occt-import-js`)
3. `python3 tools/check_step_agreement.py out3d/sierrathon_parts.json`
Report the number of bodies and the largest difference. This is a test, not a proof: say so.
