# Checklist qualite — WinBoost

## Avant chaque push
- [ ] Tests passent (`pytest`)
- [ ] Pas de secrets dans le code
- [ ] Ruff lint clean (`ruff check .`)
- [ ] Couverture > 80% (`pytest --cov`)
- [ ] Pas de fichier systeme modifie sans backup
- [ ] Dry-run teste pour toute nouvelle action

## Avant chaque release
- [ ] Build PyInstaller fonctionne
- [ ] .exe teste sur Windows 10 + Windows 11
- [ ] Toutes les actions ont un rollback fonctionnel
- [ ] README a jour avec screenshots
- [ ] CHANGELOG a jour
- [ ] status.yaml a jour
