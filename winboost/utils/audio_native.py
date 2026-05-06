"""Helpers audio natifs Windows via pycaw + Core Audio API.

Permet :
- get_volume() / set_volume(level: int 0-100) precis
- is_muted() / set_mute(muted: bool) strict (pas un toggle)
- toggle_mute() pour conserver la semantique historique
- get_default_device() / list_devices()

pycaw est dans extra `audio` (pas dans le core pour ne pas alourdir le .exe).

Pourquoi pycaw plutot que SendKeys ?
1. Mute STRICT : `set_mute(True)` mute toujours, alors que SendKeys VK_VOLUME_MUTE
   est un toggle (re-pressing remet le son). Impossible de garantir l'etat final.
2. Volume PRECIS : `set_volume(50)` met exactement 50%, alors que SendKeys empile
   N pressions VolumeDown puis M pressions VolumeUp -> approximation grossiere
   et incompatible avec un controle audio externe (SoundVolumeView, AutoHotkey).

Pattern d'usage :
    from winboost.utils.audio_native import set_volume, set_mute, AudioNativeError

    try:
        set_volume(50)       # exactement 50%
        set_mute(True)       # mute strict, pas un toggle
    except AudioNativeError as exc:
        logger.warning(f"Audio native indisponible : {exc}")
        # fallback SendKeys (existant via app_011-015)
"""

from __future__ import annotations

from typing import Any


class AudioNativeError(RuntimeError):
    """Levee quand un helper audio natif echoue (pycaw absent, COM, device).

    Le message contient toujours une indication actionnable :
    - "pip install winboost[audio]" si pycaw n'est pas installe
    - description du device ou de l'erreur COM sinon
    """


_PYCAW_INSTALL_HINT = (
    "pycaw n'est pas installe. Installe-le via : pip install winboost[audio]"
)


def _import_pycaw() -> tuple[Any, Any, Any]:
    """Importe pycaw paresseusement et leve AudioNativeError si absent.

    Returns:
        (AudioUtilities, IAudioEndpointVolume, cast) — les 3 symboles utiles.

    Raises:
        AudioNativeError: Si pycaw ou comtypes n'est pas installable.
    """
    try:
        from comtypes import cast  # type: ignore  # noqa: I001
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
    except ImportError as exc:
        raise AudioNativeError(_PYCAW_INSTALL_HINT) from exc
    # On retourne les noms pycaw tels quels (PascalCase officiel pycaw)
    return AudioUtilities, IAudioEndpointVolume, cast  # noqa: N806


def _get_endpoint_volume() -> Any:
    """Recupere l'interface IAudioEndpointVolume du device de sortie par defaut.

    Returns:
        Une instance IAudioEndpointVolume prete a etre utilisee.

    Raises:
        AudioNativeError: Si pycaw absent, ou si le device est introuvable, ou
            si l'instanciation COM echoue (service audio Windows arrete, etc.).
    """
    AudioUtilities, IAudioEndpointVolume, cast = _import_pycaw()

    try:
        # comtypes.POINTER + IID — pycaw expose le helper directement
        from comtypes import CLSCTX_ALL, POINTER  # type: ignore
    except ImportError as exc:
        raise AudioNativeError(
            "comtypes incomplet — reinstalle pycaw : pip install --upgrade winboost[audio]"
        ) from exc

    try:
        devices = AudioUtilities.GetSpeakers()
        if devices is None:
            raise AudioNativeError(
                "Aucun device de sortie audio par defaut (service audio arrete ?)"
            )
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except AudioNativeError:
        raise
    except Exception as exc:  # noqa: BLE001 — on englobe COMError + tout le reste
        raise AudioNativeError(
            f"Impossible d'activer l'interface audio Windows : {exc}"
        ) from exc


def _clamp_volume(level: int) -> int:
    """Clamp un niveau de volume entre 0 et 100.

    Raises:
        ValueError: Si level n'est pas un int (les float et str sont rejetes).
    """
    if not isinstance(level, int) or isinstance(level, bool):
        raise ValueError(
            f"level doit etre un int entre 0 et 100, recu {type(level).__name__}"
        )
    return max(0, min(100, level))


def get_volume() -> int:
    """Lit le volume du device de sortie par defaut (0-100).

    Returns:
        Niveau de volume entre 0 et 100 (entier arrondi).

    Raises:
        AudioNativeError: Si pycaw absent ou device introuvable.
    """
    endpoint = _get_endpoint_volume()
    try:
        scalar = endpoint.GetMasterVolumeLevelScalar()
    except Exception as exc:  # noqa: BLE001
        raise AudioNativeError(f"Lecture volume echouee : {exc}") from exc
    # GetMasterVolumeLevelScalar retourne un float [0.0, 1.0]
    return int(round(float(scalar) * 100))


def set_volume(level: int) -> None:
    """Regle le volume du device de sortie par defaut a level (0-100).

    Args:
        level: Niveau cible entre 0 et 100. Clampe dans cet intervalle.

    Raises:
        ValueError: Si level n'est pas un int.
        AudioNativeError: Si pycaw absent ou device introuvable.
    """
    clamped = _clamp_volume(level)
    endpoint = _get_endpoint_volume()
    try:
        endpoint.SetMasterVolumeLevelScalar(clamped / 100.0, None)
    except Exception as exc:  # noqa: BLE001
        raise AudioNativeError(
            f"Ecriture volume echouee (level={clamped}) : {exc}"
        ) from exc


def is_muted() -> bool:
    """Retourne True si le device de sortie par defaut est mute.

    Raises:
        AudioNativeError: Si pycaw absent ou device introuvable.
    """
    endpoint = _get_endpoint_volume()
    try:
        return bool(endpoint.GetMute())
    except Exception as exc:  # noqa: BLE001
        raise AudioNativeError(f"Lecture mute echouee : {exc}") from exc


def set_mute(muted: bool) -> None:
    """Regle l'etat mute du device de sortie par defaut, STRICT (pas un toggle).

    `set_mute(True)` mute toujours, meme si le device est deja mute.
    `set_mute(False)` unmute toujours, meme si le device est deja unmute.

    Args:
        muted: True pour couper le son, False pour le retablir.

    Raises:
        AudioNativeError: Si pycaw absent ou device introuvable.
    """
    endpoint = _get_endpoint_volume()
    try:
        # SetMute attend un BOOL Win32 (1/0), pas un bool Python — on cast explicite
        endpoint.SetMute(1 if muted else 0, None)
    except Exception as exc:  # noqa: BLE001
        raise AudioNativeError(
            f"Ecriture mute echouee (muted={muted}) : {exc}"
        ) from exc


def toggle_mute() -> bool:
    """Inverse l'etat mute du device de sortie par defaut.

    Returns:
        Le NOUVEL etat (True = mute apres l'operation, False = unmute).

    Raises:
        AudioNativeError: Si pycaw absent ou device introuvable.
    """
    new_state = not is_muted()
    set_mute(new_state)
    return new_state


def get_default_device() -> dict[str, Any]:
    """Retourne les informations du device de sortie par defaut.

    Returns:
        dict avec les cles :
            - "name": str — nom convivial (FriendlyName)
            - "id": str — identifiant unique du device
            - "volume": int — volume actuel (0-100)
            - "muted": bool — etat mute actuel

    Raises:
        AudioNativeError: Si pycaw absent ou device introuvable.
    """
    AudioUtilities, _IAudioEndpointVolume, _cast = _import_pycaw()

    try:
        devices = AudioUtilities.GetSpeakers()
    except Exception as exc:  # noqa: BLE001
        raise AudioNativeError(
            f"Impossible de recuperer le device par defaut : {exc}"
        ) from exc
    if devices is None:
        raise AudioNativeError("Aucun device de sortie audio par defaut")

    name: str = ""
    device_id: str = ""
    try:
        device_id = str(devices.GetId() or "")
    except Exception:  # noqa: BLE001
        device_id = ""

    # FriendlyName via PropertyStore — best effort, ne casse pas si absent.
    # On reutilise AudioUtilities deja resolu plus haut pour respecter les mocks
    # injectes par les tests (pas de re-import direct).
    try:
        all_devices = AudioUtilities.GetAllDevices() or []
        for dev in all_devices:
            try:
                if str(getattr(dev, "id", "") or "") == device_id and getattr(
                    dev, "FriendlyName", None
                ):
                    name = str(dev.FriendlyName)
                    break
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        name = ""

    return {
        "name": name,
        "id": device_id,
        "volume": get_volume(),
        "muted": is_muted(),
    }


def list_devices() -> list[dict[str, Any]]:
    """Liste tous les devices audio (entree + sortie).

    Returns:
        Liste de dicts {"name": str, "id": str, "state": str}.

    Raises:
        AudioNativeError: Si pycaw absent.
    """
    AudioUtilities, _IAudioEndpointVolume, _cast = _import_pycaw()

    try:
        all_devices = AudioUtilities.GetAllDevices()
    except Exception as exc:  # noqa: BLE001
        raise AudioNativeError(f"Listing devices echoue : {exc}") from exc

    result: list[dict[str, Any]] = []
    for dev in all_devices or []:
        try:
            result.append(
                {
                    "name": str(getattr(dev, "FriendlyName", "") or ""),
                    "id": str(getattr(dev, "id", "") or ""),
                    "state": str(getattr(dev, "state", "") or ""),
                }
            )
        except Exception:  # noqa: BLE001
            continue
    return result
