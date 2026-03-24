# Prompt Phase 1 — Foundation

## Contexte
WinBoost est un outil Python standalone Windows d'optimisation systeme.
Phase 1 = core architecture + 2 premiers modules + CLI.

## Taches
1. Implementer `core/base_module.py` — classe abstraite BaseModule avec :
   - name, description, risk_level (proprietes)
   - scan() -> ScanResult (analyse sans modification)
   - fix(scan_result) -> FixResult (applique les corrections)
   - preview(scan_result) -> str (description humaine)

2. Implementer `core/engine.py` — orchestrateur :
   - Charge tous les modules dynamiquement
   - scan_all() / scan_module(name)
   - fix_module(name, scan_result)

3. Implementer `core/config.py` — settings JSON locale

4. Implementer `modules/temp_cleaner.py` — nettoyage fichiers temp Windows

5. Implementer `modules/system_info.py` — infos systeme (CPU, RAM, disque, OS)

6. Implementer `cli/main.py` — Click CLI (scan, fix, info)

7. Tests pytest pour tout

## Livrable attendu
`winboost scan --module temp` fonctionne et affiche les resultats.
