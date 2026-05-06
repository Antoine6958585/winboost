# docs/assets — Captures et demos

Ce dossier contient les binaires de documentation referencees depuis le `README.md` racine et les futurs guides : GIFs de demo, screenshots, schemas exportes.

## Convention de nommage

```
winboost-{feature}-{type}.{ext}
```

Exemples : `winboost-overlay-demo.gif`, `winboost-chat-screenshot.png`, `winboost-architecture-diagram.svg`.

## Capture du GIF overlay (`winboost-overlay-demo.gif`)

Le `README.md` reference `docs/assets/winboost-overlay-demo.gif`. Pour le recapturer :

### Scenario (5-8 secondes)

1. Terminal ouvert, lancer `winboost overlay` (admin si necessaire)
2. Basculer sur une application quelconque (Chrome, VS Code, Slack)
3. Presser **Ctrl+Alt+Espace** : l'overlay apparait centre
4. Taper `active le mode focus`
5. Presser Enter : l'action proposee s'affiche inline
6. Presser **Esc** : l'overlay se ferme

### Outils suggeres (Windows)

- **ScreenToGif** ([screentogif.com](https://www.screentogif.com)) — gratuit, leger, export GIF natif, decoupe par image. Recommande.
- **ShareX** ([getsharex.com](https://getsharex.com)) — screen recorder + export GIF, plus complet mais plus lourd.
- **ffmpeg** — pour optimiser un GIF deja capture :
  ```bash
  ffmpeg -i input.mp4 -vf "fps=15,scale=720:-1:flags=lanczos" -c:v gif output.gif
  ```

### Contraintes

- **Largeur max** : 800 px (lisible sur GitHub mobile et desktop)
- **Duree** : 5 a 10 secondes (boucle infinie)
- **Poids** : viser <2 Mo (compresser avec `gifsicle -O3` si necessaire)
- **FPS** : 12-15 suffit pour une demo CLI/overlay (pas besoin de 30 FPS)

### Validation

Une fois le GIF dans ce dossier, verifier le rendu sur la preview GitHub du `README.md` (lien direct : `https://github.com/Antoine6958585/winboost/blob/main/README.md`).
