"""Prüfung des vom Browser gesendeten Gesprächsverlaufs."""

ROLLEN = {"lokal": ("user", "assistant", "tool"), "claude": ("user", "assistant")}


def pruefe_verlauf(verlauf, max_nachrichten, rollen=("user", "assistant")):
    """Prüft den Verlauf grob auf Form. Liefert die bereinigte Liste."""
    if verlauf is None:
        return []
    if not isinstance(verlauf, list):
        raise ValueError("verlauf muss eine Liste sein")
    if len(verlauf) > max_nachrichten:
        raise ValueError(f"Der Verlauf ist zu lang (max. {max_nachrichten} Nachrichten). Bitte neues Gespräch beginnen.")
    for n in verlauf:
        if not isinstance(n, dict) or n.get("role") not in rollen:
            raise ValueError(f"Jede Nachricht braucht role {'/'.join(rollen)}")
        if not isinstance(n.get("content"), (str, list)):
            raise ValueError("Nachricht ohne content")
    if verlauf and verlauf[0]["role"] != "user":
        raise ValueError("Der Verlauf muss mit einer Nutzernachricht beginnen")
    return verlauf


def erzeuge_assistent(konfig, wissen_text):
    """Baut den Assistenten passend zu konfig.backend."""
    if konfig.backend == "claude":
        from .ki import Assistent  # importiert das anthropic-SDK erst hier
        return Assistent(konfig, wissen_text)
    from .ki_lokal import LokalerAssistent
    return LokalerAssistent(konfig, wissen_text)
