# WinBoost — MASTER PLAN

## Vision
"Le premier assistant Windows qui ne te ment pas."

v1 = 8 modules classiques (temp cleaner, startup, RAM, disk, privacy, dev cache, services, system info)
v2 = Chat IA conversationnel qui pilote le PC via un Action Registry de 150+ actions

## Positionnement
Copilot ne touche pas au systeme. Les optimizers ne parlent pas. WinBoost fait les deux.

## Modele de revenus
- Gratuit : v1 complete + chat IA 50 actions
- Pro (4.99 EUR/mois ou 39 EUR/an) : 150+ actions, profils, rollback avance, support
- BYO key : gratuit, sans limite

## Cible
Power users Windows, developpeurs, admins IT, puis utilisateurs intermediaires via v2.

## Stack
Python 3.12+ | CustomTkinter | Click | psutil/wmi/ctypes | Anthropic/OpenAI/Ollama | PyInstaller | pytest

## Milestones
- v1.0 : 8 modules + CLI + GUI + .exe (Phases 1-5)
- v2.0 : Action Registry + AI Engine + Chat GUI (Phases 6-10)

## Regles absolues
1. Pas de modification registre sans backup
2. Pas de suppression fichier systeme
3. Dry-run par defaut
4. L'IA ne peut jamais agir sans confirmation
5. Tout est reversible
