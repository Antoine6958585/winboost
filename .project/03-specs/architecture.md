# Architecture — WinBoost

## Vue d'ensemble

```
GUI Layer (CustomTkinter) | Chat Layer | CLI Layer (Click)
                    |
               AI Engine
    NL Parser -> Action Router -> Safety Engine
                    |
            Action Registry (150+ YAML)
                    |
            Execution Engine
    Preview (dry-run) -> Execute -> Backup & Rollback
                    |
            Module Layer (v1)
    temp | startup | ram | disk | privacy | dev | service | sysinfo
                    |
            Windows APIs
    psutil | wmi | ctypes | subprocess | winreg | DISM
```

## Safety Levels
- info (bleu) : lecture seule
- low (vert) : confirmation simple
- medium (jaune) : preview + explication + confirmation
- high (orange) : warning + dry-run + double confirm
- critical (rouge) : bloque par defaut

## Action Registry Format
Chaque action = fichier YAML dans actions/{categorie}/ :
- id, name, description, category, risk_level
- requires_admin, reversible
- preview (before/after/impact)
- execute (method + commands)
- rollback (commands)
- keywords (fr/en)
- compatibility (min_version, editions)

## LLM Integration
- Provider abstraction (Anthropic/OpenAI/Ollama)
- Cache local : keyword matching avant LLM call
- Estimation : 70% des requetes resolues sans LLM
- BYO key supporte
