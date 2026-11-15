from collections.abc import Mapping


def agent_mode(environ: Mapping[str, str], tty: bool) -> tuple[bool, str]:
    override = environ.get("LADDER_AGENT")
    if override == "1":
        return True, "LADDER_AGENT=1"
    if override == "0":
        return False, "LADDER_AGENT=0"
    if environ.get("CLAUDECODE"):
        if not tty:
            return True, "CLAUDECODE set, no TTY"
        return False, "CLAUDECODE set, but a TTY is present"
    return False, "no agent signal"
