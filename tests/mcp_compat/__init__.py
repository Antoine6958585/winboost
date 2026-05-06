"""POC de compatibilite PyInstaller + transport stdio JSON-RPC (T072).

Ce dossier contient un mini-serveur stdio en Python pur (pas FastMCP) et
un client subprocess pour valider empiriquement si un binaire PyInstaller
peut servir de transport stdio fiable pour un serveur MCP.

Le test isole la couche transport :
- protocole simple ligne-JSON (une requete = une ligne, une reponse = une ligne)
- binarisation via PyInstaller en console mode + onefile
- comparaison Python script vs .exe sur 3 requetes test

Verdict consigne dans VERDICT.md.
"""
