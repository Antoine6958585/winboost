"""Theme network — diagnostics reseau de base.

Couverture :

1. Adapter principal Up (Get-NetAdapter)
2. Resolution DNS (`nslookup google.com`)
3. Gateway accessible (ping de la gateway)
4. Service `Dnscache`
5. Conflits IPv6 vs IPv4 (les 2 actifs simultanement peuvent causer des
   timeouts sur certains FAI)
"""

from __future__ import annotations

from typing import Any

from winboost.diagnose.checks import (
    Check,
    CheckResult,
    Severity,
    run_ps_check,
    service_status,
)
from winboost.utils.windows_native import WindowsNativeError


class NetAdapterCheck(Check):
    """Verifie qu'au moins un adapter reseau est Up."""

    name = "network_adapter_status"

    def run(self) -> CheckResult:
        cmd = (
            "Get-NetAdapter -ErrorAction SilentlyContinue "
            "| Where-Object { $_.Status -eq 'Up' -and $_.Virtual -eq $false } "
            "| Select-Object Name, InterfaceDescription, Status, LinkSpeed "
            "| ConvertTo-Csv -NoTypeInformation"
        )
        try:
            result = run_ps_check(cmd, timeout=5.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Lecture adapters impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        if not result.ok:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Lecture adapters echouee",
                details={"stderr": result.stderr},
                suggested_actions=(),
            )

        lines = [line for line in result.stdout.splitlines() if line.strip()]
        adapters = lines[1:] if len(lines) > 1 else []
        details: dict[str, Any] = {"adapters_up_count": len(adapters)}

        if not adapters:
            return CheckResult(
                name=self.name,
                severity=Severity.CRITICAL.value,
                message="Aucun adapter reseau actif (ni Wi-Fi ni Ethernet) — pas de connexion",
                details=details,
                suggested_actions=("net_020",),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"{len(adapters)} adapter(s) reseau actif(s)",
            details=details,
            suggested_actions=(),
        )


class DnsResolutionCheck(Check):
    """Tente une resolution DNS via Resolve-DnsName."""

    name = "network_dns_resolution"

    def run(self) -> CheckResult:
        cmd = (
            "try { "
            "  $r = Resolve-DnsName 'google.com' -Type A -ErrorAction Stop; "
            "  $r[0].IPAddress "
            "} catch { 'DNS_FAIL: ' + $_.Exception.Message }"
        )
        try:
            result = run_ps_check(cmd, timeout=10.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Test DNS impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        out = result.stdout.strip()
        if out.startswith("DNS_FAIL"):
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message=f"Resolution DNS de google.com echouee : {out[10:]}",
                details={"raw": out},
                suggested_actions=("net_014", "net_015"),
            )

        if not out:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message="Pas de reponse DNS (sortie vide)",
                details={"raw": out},
                suggested_actions=("net_014",),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message=f"DNS OK (google.com -> {out.splitlines()[0]})",
            details={"resolved": out.splitlines()[0]},
            suggested_actions=(),
        )


class GatewayPingCheck(Check):
    """Ping la gateway par defaut pour valider le routage local."""

    name = "network_gateway_ping"

    def run(self) -> CheckResult:
        cmd = (
            "$gw = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' "
            "      -ErrorAction SilentlyContinue | Sort-Object RouteMetric "
            "      | Select-Object -First 1).NextHop; "
            "if (-not $gw) { 'NO_GATEWAY' } "
            "else { Test-Connection -ComputerName $gw -Count 1 -Quiet "
            "       -ErrorAction SilentlyContinue }"
        )
        try:
            result = run_ps_check(cmd, timeout=10.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Test gateway impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        out = result.stdout.strip()
        if out == "NO_GATEWAY":
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message="Aucune gateway par defaut configuree",
                details={"raw": out},
                suggested_actions=("net_016",),
            )
        if out.lower() == "true":
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="Gateway accessible (ping OK)",
                details={"raw": out},
                suggested_actions=(),
            )
        if out.lower() == "false":
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message="Gateway injoignable (ping KO) — probleme local ou routeur",
                details={"raw": out},
                suggested_actions=("net_013",),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.WARNING.value,
            message=f"Reponse ping gateway inattendue : {out!r}",
            details={"raw": out},
            suggested_actions=(),
        )


class DnscacheServiceCheck(Check):
    """Verifie le service `Dnscache` (cache DNS Windows)."""

    name = "network_dnscache_service"

    def run(self) -> CheckResult:
        status = service_status("Dnscache")
        details = {"service": "Dnscache", "status": status}

        if status == "running":
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message="Service Dnscache en cours d'execution",
                details=details,
                suggested_actions=(),
            )
        if status in {"stopped", "stop_pending"}:
            return CheckResult(
                name=self.name,
                severity=Severity.ERROR.value,
                message=f"Service Dnscache arrete ({status}) — resolutions DNS lentes",
                details=details,
                suggested_actions=("net_014",),
            )
        return CheckResult(
            name=self.name,
            severity=Severity.WARNING.value,
            message=f"Service Dnscache dans un etat inhabituel : {status}",
            details=details,
            suggested_actions=(),
        )


class IPv6ConflictCheck(Check):
    """Detecte si IPv6 est actif sur les adapters Up.

    On ne flag pas systematiquement comme erreur : certains FAI gerent IPv6
    proprement. On signale en INFO/WARNING si les 2 sont actifs.
    """

    name = "network_ipv6_status"

    def run(self) -> CheckResult:
        cmd = (
            "Get-NetAdapterBinding -ComponentID 'ms_tcpip6' "
            "-ErrorAction SilentlyContinue "
            "| Where-Object { $_.Enabled -eq $true } "
            "| Measure-Object | Select-Object -ExpandProperty Count"
        )
        try:
            result = run_ps_check(cmd, timeout=5.0)
        except WindowsNativeError as exc:
            return CheckResult(
                name=self.name,
                severity=Severity.WARNING.value,
                message=f"Test IPv6 impossible : {exc}",
                details={"error": str(exc)},
                suggested_actions=(),
            )

        out = result.stdout.strip()
        try:
            count = int(out) if out else 0
        except ValueError:
            count = 0

        details = {"ipv6_enabled_adapters": count}
        if count > 0:
            return CheckResult(
                name=self.name,
                severity=Severity.OK.value,
                message=(
                    f"IPv6 actif sur {count} adapter(s) — desactiver via net_017 "
                    "uniquement si symptomes de timeout"
                ),
                details=details,
                suggested_actions=(),
            )

        return CheckResult(
            name=self.name,
            severity=Severity.OK.value,
            message="IPv6 desactive sur tous les adapters",
            details=details,
            suggested_actions=(),
        )


def get_checks() -> list[Check]:
    """Retourne la liste ordonnee des checks network."""
    return [
        NetAdapterCheck(),
        DnsResolutionCheck(),
        GatewayPingCheck(),
        DnscacheServiceCheck(),
        IPv6ConflictCheck(),
    ]
